"""Curated real cache and bounded NASA POWER point acquisition; no silent fixtures."""
import calendar
import hashlib
import json
import math
import time
import urllib.parse
import urllib.request
from datetime import date,timedelta
from pathlib import Path

from ..core import timestamp,write_json
from .inputs import geometry_info,fingerprint

RESOURCES=Path(__file__).resolve().parents[1]/'resources/agrotwin'


def load(name):return json.loads((RESOURCES/name).read_text(encoding='utf-8'))


def numeric(value):
    if value is None or str(value).strip()=='':return None
    if isinstance(value,bool):raise ValueError('Boolean is not a measurement')
    value=float(value)
    if not math.isfinite(value):raise ValueError('Nonfinite measurement')
    return None if value in (-999.,-9999.) else value


def qualify(rows,period,flags=()):
    result=[];seen=set();cursor=period.start
    for row in rows:
        key=row['date']
        if key in seen:raise ValueError('Duplicate month in D1')
        seen.add(key)
        d=date.fromisoformat(key)
        if d.day!=1:raise ValueError('Month start required')
        if not period.start<=d<period.end:continue
        rain,temp=numeric(row['rain']),numeric(row['temp'])
        coverage=numeric(row.get('coverage'))
        if coverage is None or not 0<=coverage<=1:raise ValueError('Invalid monthly coverage')
        if rain is not None and rain<0:raise ValueError('Negative precipitation')
        rain_coverage=numeric(row.get('rain_coverage',coverage))
        temp_coverage=numeric(row.get('temp_coverage',coverage))
        if any(v is None or not 0<=v<=1 for v in (rain_coverage,temp_coverage)):raise ValueError('Invalid variable coverage')
        if abs(coverage-min(rain_coverage,temp_coverage))>1e-9:raise ValueError('Inconsistent monthly coverage')
        if rain_coverage<1 and rain is not None:raise ValueError('Incomplete precipitation cannot be a monthly total')
        relevant=[f for f in flags if f['date'][:7]==key[:7]]
        qa=row.get('qa','warn')
        if qa not in ('pass','warn','fail','partial'):raise ValueError('Unknown source QA state')
        qa='fail' if qa=='fail' else 'warn' if relevant or qa!='pass' or coverage<1 or rain is None or temp is None else 'pass'
        result.append({'date':key,'rain':rain,'temp':temp,'coverage':coverage,'qa':qa,'flags':relevant,
                       'rain_coverage':rain_coverage,'temp_coverage':temp_coverage})
    present={r['date'] for r in result}
    while cursor<period.end:
        key=cursor.isoformat()
        if key not in present:result.append({'date':key,'rain':None,'temp':None,'coverage':0,'qa':'fail','flags':[]})
        cursor=date(cursor.year+1,1,1) if cursor.month==12 else date(cursor.year,cursor.month+1,1)
    return sorted(result,key=lambda r:r['date'])


def daily_months(raw,period):
    if raw.get('header',{}).get('time_standard')!='UTC':raise ValueError('NASA response must use UTC')
    parameters=raw['properties']['parameter'];metadata=raw['parameters']
    if metadata['T2M']['units']!='C' or metadata['PRECTOTCORR']['units']!='mm/day':raise ValueError('Unverified source units')
    rows=[];cursor=period.start
    while cursor<period.end:
        count=calendar.monthrange(cursor.year,cursor.month)[1];rain=[];temp=[]
        for day in range(count):
            key=(cursor+timedelta(days=day)).strftime('%Y%m%d')
            rain.append(numeric(parameters['PRECTOTCORR'].get(key)))
            temp.append(numeric(parameters['T2M'].get(key)))
        rain_coverage=sum(v is not None for v in rain)/count
        temp_coverage=sum(v is not None for v in temp)/count
        coverage=min(rain_coverage,temp_coverage)
        rows.append({'date':cursor.isoformat(),'rain':sum(rain) if all(v is not None for v in rain) else None,
                     'temp':sum(temp)/count if all(v is not None for v in temp) else None,'coverage':coverage,
                     'rain_coverage':rain_coverage,'temp_coverage':temp_coverage,'qa':'pass' if coverage==1 else 'warn'})
        cursor=date(cursor.year+1,1,1) if cursor.month==12 else date(cursor.year,cursor.month+1,1)
    return qualify(rows,period)


def fetch_power(request,store):
    center=geometry_info(request.geometry)['centroid']
    params={'parameters':'T2M,PRECTOTCORR','community':'AG','longitude':f'{center[0]:.6f}','latitude':f'{center[1]:.6f}',
            'start':request.period.start.strftime('%Y%m%d'),'end':(request.period.end-timedelta(days=1)).strftime('%Y%m%d'),
            'format':'JSON','time-standard':'UTC'}
    url='https://power.larc.nasa.gov/api/temporal/daily/point?'+urllib.parse.urlencode(params)
    for attempt in range(2):
        try:
            with urllib.request.urlopen(url,timeout=8) as response:
                data=response.read(4_000_001)
                if len(data)>4_000_000:raise ValueError('Source response exceeds 4 MB')
            raw=json.loads(data);rows=daily_months(raw,request.period)
            digest=hashlib.sha256(data).hexdigest();folder=Path(store)/'sources';folder.mkdir(parents=True,exist_ok=True)
            target=folder/(digest+'.json')
            if not target.exists():
                with target.open('xb') as f:f.write(data)
            return rows,{'id':'NASA-POWER-LIVE','url':url,'sha256':digest,'retrieved_at':timestamp(),
                         'provider':'NASA POWER','product':'Daily API UTC T2M/PRECTOTCORR','evidence_class':'DERIVED_MODEL',
                         'native_resolution':'Source-native coarse meteorological grid; not field measurements',
                         'query_point_lon_lat':center,'acquisition':'downloaded_new','observed_period':request.period.model_dump(mode='json')}
        except Exception:
            if attempt==1:raise
            time.sleep(.3)


def acquire(request,store):
    cache=load('climate.json');case=load('case.json')
    same=geometry_info(request.geometry)['geometry_hash']==geometry_info(case['geometry'])['geometry_hash']
    query_key=fingerprint({'geometry':geometry_info(request.geometry)['geometry_hash'],'period':request.period.model_dump(mode='json')})
    query_cache=Path(store)/'source-index'/(query_key+'.json')
    if query_cache.is_file() and request.source_mode!='live':
        saved=json.loads(query_cache.read_text(encoding='utf-8'))
        return {'months':qualify(saved['months'],request.period),'source':{**saved['source'],'acquisition':'versioned_cache'},
                'warnings':[],'catalog_supported':same}
    error=None
    if request.source_mode=='live' or (not same and request.source_mode!='offline'):
        try:
            rows,source=fetch_power(request,store)
            write_json(query_cache,{'months':rows,'source':source})
            return {'months':rows,'source':source,'warnings':[],'catalog_supported':same}
        except Exception as ex:error=f'NASA acquisition unavailable ({type(ex).__name__}); no TLS bypass or synthetic substitution.'
    if same:
        rows=qualify(cache['months'],request.period,cache['source']['flags'])
        return {'months':rows,'source':{**cache['source'],'acquisition':'versioned_cache'},
                'warnings':[error] if error else [],'catalog_supported':True}
    return {'months':qualify([],request.period),'source':None,'warnings':[error or 'Offline source cache is available only for the original Mỹ Thành study geometry.'],
            'catalog_supported':False}
