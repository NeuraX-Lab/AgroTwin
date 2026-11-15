"""NASA POWER daily point precipitation/T2M -> monthly NeuraX D1 contract.

Supports NASA POWER JSON or the standard daily CSV with YEAR/MO/DY header.
No automatic geographic resampling or soil/crop inference is performed.
"""
from __future__ import annotations
import calendar,csv,json,math
from collections import defaultdict
from pathlib import Path
from datetime import date
from .core import write_json,sha256_file,timestamp

MISSING_CODES={-999.,-9999.,-99.}

def number(x):
    if x is None or str(x).strip()=='':return None
    try:v=float(x)
    except (TypeError,ValueError):return None
    return None if v in MISSING_CODES or not math.isfinite(v) else v

def read_power_daily(path):
    path=Path(path)
    if path.suffix.lower()=='.json':
        with path.open(encoding='utf-8-sig') as f:j=json.load(f)
        params=(j.get('properties') or {}).get('parameter') or {}
        if not params:raise ValueError('No POWER properties.parameter in JSON')
        rain=params.get('PRECTOTCORR') or params.get('PRECTOT')
        temp=params.get('T2M')
        if rain is None and temp is None:raise ValueError('No PRECTOTCORR/PRECTOT/T2M in NASA POWER JSON')
        keys=sorted(set((rain or {}).keys())|set((temp or {}).keys()))
        out=[]
        for key in keys:
            if not (len(key)==8 and key.isdigit()):continue
            out.append((date.fromisoformat(f'{key[:4]}-{key[4:6]}-{key[6:]}'),
                        number((rain or {}).get(key)),number((temp or {}).get(key))))
        unit_meta=((j.get('parameters') or {}))
        return out,{'raw_parameters':list(params),'source_format':'POWER daily JSON','parameter_metadata':unit_meta}
    if path.suffix.lower()!='.csv':raise ValueError('POWER adapter accepts CSV or JSON only')
    with path.open('r',encoding='utf-8-sig',errors='replace',newline='') as f:
        lines=[]
        for line in f:
            if line.strip().lstrip('"').upper().startswith('YEAR,') or line.strip().lstrip('"').upper().startswith('YEAR;'):
                lines.append(line);break
        if not lines:raise ValueError('NASA POWER CSV header YEAR,MO,DY not found')
        lines.extend(f)
    r=csv.DictReader(lines)
    if not r.fieldnames or not {'YEAR','MO','DY'}.issubset(r.fieldnames):
        raise ValueError('Missing YEAR/MO/DY columns')
    if not (set(r.fieldnames)&{'T2M','PRECTOTCORR','PRECTOT'}):
        raise ValueError('No supported climate parameter columns')
    out=[]
    for row in r:
        if not row.get('YEAR'):continue
        d=date(int(row['YEAR']),int(row['MO']),int(row['DY']))
        out.append((d,number(row.get('PRECTOTCORR',row.get('PRECTOT'))),number(row.get('T2M'))))
    return out,{'raw_parameters':list(r.fieldnames),'source_format':'POWER daily CSV'}


def _write_csv(path,header,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f);w.writerow(header);w.writerows(rows)


def normalize_power(inp:Path,region_id:str,out:Path,source_manifest:Path|None=None):
    inp=Path(inp).resolve();out=Path(out).resolve()
    if not region_id or not region_id.strip():raise ValueError('region_id cannot be empty')
    src={}
    if source_manifest:
        src=json.loads(Path(source_manifest).read_text(encoding='utf-8'))
    daily,origin=read_power_daily(inp)
    if not daily:raise ValueError('No daily records in source file')
    dates=[r[0] for r in daily]
    if len(dates)!=len(set(dates)):raise ValueError('Duplicate daily dates in POWER source; refuse implicit aggregation')
    per=defaultdict(list)
    for d,rain,temp in daily:
        if rain is not None and rain < 0:raise ValueError(f'Negative daily precipitation on {d}; inspect source units')
        per[d.year,d.month].append((rain,temp))
    rows=[];qa=[]
    for (year,month),records in sorted(per.items()):
        n=calendar.monthrange(year,month)[1]
        r=[x for x,_ in records if x is not None]
        t=[x for _,x in records if x is not None]
        rc=len(r)/n;tc=len(t)/n
        # Do not present partial-month sums as complete rainfall totals.
        p=sum(r) if rc==1 else None
        temp=sum(t)/len(t) if tc==1 and t else None
        start=date(year,month,1)
        end=date(year+1,1,1) if month==12 else date(year,month+1,1)
        status='pass' if rc==1 and tc==1 else 'partial'
        rows.append([region_id,start.isoformat(),end.isoformat(),round(p,6) if p is not None else '',
                     round(temp,6) if temp is not None else '',round(rc,4),round(tc,4),status])
        qa.append([region_id,start.isoformat(),len(records),n,len(r),len(t),status,
                   'Complete monthly total only if all calendar days valid; never replace missing with zero'])
    out.mkdir(parents=True,exist_ok=True)
    _write_csv(out/'features.csv',
        ['region_id','period_start','period_end','precip_sum_mm','air_temp_mean_c','precip_coverage','temp_coverage','qa_status'],rows)
    _write_csv(out/'qa-summary.csv',
        ['region_id','period_start','observed_days','calendar_days','valid_precip_days','valid_temp_days','qa_status','note'],qa)
    dictionary=[
        ['region_id','string','','analysis area identifier'],
        ['period_start','date','ISO 8601','calendar month start'],
        ['period_end','date','ISO 8601','exclusive month end'],
        ['precip_sum_mm','float','mm/month','sum of daily precipitation only with 100% daily coverage'],
        ['air_temp_mean_c','float','degrees C','monthly mean of daily air temperature with full coverage'],
        ['precip_coverage','float','0..1','valid daily precipitation / calendar days'],
        ['temp_coverage','float','0..1','valid daily temperature / calendar days'],
        ['qa_status','enum','','pass or partial; QA reviewer approval still required']]
    _write_csv(out/'dictionary.csv',['column','dtype','unit','definition'],dictionary)
    _write_csv(out/'provenance.csv',['file','source_file','provider','product','source_url','review_status'],[
        ['features.csv',str(inp),src.get('provider','unknown'),src.get('product','POWER daily candidate'),
         src.get('source_url',''),src.get('verification_status','unverified')]])
    manifest={'generated_at':timestamp(),'schema_version':'D1-0.1','region_id':region_id,'data_mode':src.get('data_mode','unknown'),
       'dataset_version':(sha256_file(inp) or 'hash-unavailable')[:16], 'source_file':str(inp),
       'source_sha256':sha256_file(inp),'source_metadata':src,'reader_metadata':origin,
       'n_months':len(rows),'complete_months':sum(x[-1]=='pass' for x in rows),
       'warnings':['Units of POWER PRECTOTCORR/PRECTOT and T2M must be verified against original parameter metadata before scientific claims.',
                   'Daily timezone (POWER UTC or LST) must be checked in download request metadata.',
                   'This adapter assumes daily precipitation is mm/day, air temperature is Celsius; verify source.',
                   'No crop/soil constraints or satellite-to-field conversion done.']}
    write_json(out/'manifest.json',manifest)
    return manifest
