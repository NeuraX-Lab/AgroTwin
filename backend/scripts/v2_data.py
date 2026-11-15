"""Public-data acquisition, strict calendar QA and causal monthly features."""
import os
os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
from pathlib import Path
import sys,json,hashlib,time
import numpy as np
import pandas as pd
import requests
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from fetch_satellite_context import save,sha,now
RAW=ROOT/'data/raw/v2';DATA=ROOT/'data/processed/v2';OUT=ROOT/'runs/v2'
PROTOCOL=json.loads((ROOT/'config/v2-protocol.json').read_text(encoding='utf-8'))

def acquire():
    RAW.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    entries=[]
    for first,last in [(1984,1993),(1994,2003),(2004,2014)]:
        p=RAW/f'power-{first}-{last}.json'
        params=dict(parameters='PRECTOTCORR,T2M,T2M_MIN,T2M_MAX,RH2M',community='AG',longitude=PROTOCOL['aoi']['longitude'],latitude=PROTOCOL['aoi']['latitude'],start=f'{first}0101',end=f'{last}1231',format='JSON',**{'time-standard':'UTC'})
        url=requests.Request('GET','https://power.larc.nasa.gov/api/temporal/daily/point',params=params).prepare().url
        if not p.exists():
            r=requests.get(url,timeout=(10,180));r.raise_for_status();obj=r.json();save(p,obj)
        obj=json.loads(p.read_text(encoding='utf-8'))
        entries.append(dict(path=str(p.relative_to(ROOT)),sha256=sha(p),url=url,retrieved_at_utc=now(),header=obj['header'],license='NASA POWER open data; cite POWER and underlying MERRA2/GEOSIT; no exclusive field truth'))
        print('Cached POWER',first,last,flush=True)
    p=ROOT/'data/raw/resource-eda/power-dashboard-20261114/daily.json'
    entries.append(dict(path=str(p.relative_to(ROOT)),sha256=sha(p),url='https://power.larc.nasa.gov/api/temporal/daily/point',vintage='original v1 snapshot 2015-2026-10',license='NASA POWER open data'))
    save(RAW/'sources.json',dict(entries=entries,protocol_sha256=sha(ROOT/'config/v2-protocol.json')))

def prepare():
    DATA.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    sources=json.loads((RAW/'sources.json').read_text())['entries'];frames=[];checks=[];transforms=[]
    def check(name,ok,detail,severity='critical'):
        checks.append(dict(check=name,passed=bool(ok),severity=severity,detail=detail))
        if not ok and severity=='critical':raise ValueError(name+': '+str(detail))
    for src in sources:
        p=ROOT/src['path'];obj=json.loads(p.read_text(encoding='utf-8-sig'))
        check('source_hash_'+p.stem,sha(p)==src['sha256'],src['path'])
        check('time_standard_'+p.stem,obj['header']['time_standard']=='UTC','UTC daily boundary; local Vietnam day differs')
        check('location_'+p.stem,np.allclose(obj['geometry']['coordinates'][:2],[106.021621,10.479098],atol=.001),'Retained pack coordinate, name not independent geocoding')
        units={k:v['units'] for k,v in obj['parameters'].items()}
        check('units_'+p.stem,units['PRECTOTCORR']=='mm/day' and units['T2M']=='C' and units['RH2M']=='%',units)
        df=pd.DataFrame(obj['properties']['parameter']).astype(float);df.index=pd.to_datetime(df.index,format='%Y%m%d')
        n=int(df.eq(obj['header']['fill_value']).sum().sum());df=df.mask(df.eq(obj['header']['fill_value']))
        transforms.append(dict(source=p.name,operation='fill_to_null',cells=n,reason='documented fill value; zero retained'))
        check('duplicates_'+p.stem,not df.index.has_duplicates,len(df))
        check('physical_'+p.stem,(df.PRECTOTCORR.dropna()>=0).all() and df.RH2M.dropna().between(0,100).all() and df.T2M.dropna().between(-80,65).all(),'No plausible extremes removed')
        check('temperature_order_'+p.stem,((df.T2M_MIN<=df.T2M)&(df.T2M<=df.T2M_MAX)).all(),'Tmin <= Tmean <= Tmax')
        frames.append(df)
    daily=pd.concat(frames).sort_index();expected=pd.date_range(daily.index.min(),daily.index.max(),freq='D')
    check('cross_source_unique',not daily.index.has_duplicates,'No overlapping daily keys or many-to-many join')
    check('daily_calendar',daily.index.equals(expected),dict(rows=len(daily),expected=len(expected)))
    daily.to_csv(DATA/'daily.csv',index_label='date')
    cnt=daily.resample('MS').count();coverage=cnt.div(cnt.index.days_in_month,axis=0)
    m=daily.resample('MS').mean();m['PRECTOTCORR']=daily.PRECTOTCORR.resample('MS').sum(min_count=1)
    m=m.where(coverage.eq(1));m=m.rename(columns={'PRECTOTCORR':'precip_sum_mm','T2M':'air_temp_mean_c','RH2M':'air_rh_mean_pct'})
    check('monthly_full_coverage',coverage.eq(1).all().all(),{'rows':len(m),'missing_cells':int(m.isna().sum().sum())})
    old=pd.read_csv(ROOT/'data/processed/data-block-v1/monthly/environment.csv',index_col='period_start',parse_dates=True)
    cols=['precip_sum_mm','air_temp_mean_c','air_rh_mean_pct']
    check('v1_overlap_identity',np.allclose(m.loc[old.index,cols],old[cols],rtol=1e-10),'2015-2026 overlap exactly reproduced from raw')
    m=m.join(old[['SFMC','RZMC']],how='left',validate='one_to_one')
    m.to_csv(DATA/'monthly.csv',index_label='period_start');coverage.to_csv(DATA/'coverage.csv',index_label='period_start')
    transforms.extend([dict(operation='daily_to_monthly',input_rows=len(daily),output_rows=len(m),reason='rain sum; temperature/RH mean; full calendar denominator'),dict(operation='SMAP_left_join',input_rows=len(m),output_rows=len(m),reason='one_to_one monthly, absent early years retained null; no historical SMAP fabricated')])
    # Metamorphic leakage check: changing all future quantities cannot change origin features.
    for h in [1,3]:
        a,features=make_features(m,h,'expanded');altered=m.copy();cut=pd.Timestamp('2008-01-01');altered.loc[cut:]=9999
        b,_=make_features(altered,h,'expanded');check('future_mutation_h'+str(h),np.allclose(a.loc[:cut,features],b.loc[:cut,features],equal_nan=True),'Features at/before cutoff invariant to target/future changes')
    save(OUT/'data-qa.json',dict(created_at_utc=now(),checks=checks,transforms=transforms,daily_rows=len(daily),monthly_rows=len(m),missing=m.isna().sum().to_dict(),duplicates=0,critical_pass=True,
       label_kind='retrospective gridded estimates, not independently measured field labels',geographic_generalization=False,
       limitations=['single retained coordinate; user place-name not independently verified','SMAP L4 is assimilated model and upstream version incompletely pinned','historical release/vintage unavailable','local station records incomplete and at other sites; isolated from weather target','digitised field boundary not surveyed']))
    save(DATA/'manifest.json',dict(protocol_sha256=sha(ROOT/'config/v2-protocol.json'),sources=sources,outputs=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in [DATA/'daily.csv',DATA/'monthly.csv',DATA/'coverage.csv']],created_at_utc=now()))
    return m

def make_features(m,h,group='expanded'):
    if not m.index.equals(pd.date_range(m.index.min(),m.index.max(),freq='MS')):
        raise ValueError('Reindex to a complete monthly calendar before computing lags')
    # target month t; lead h from origin t-h; plus one month publication buffer.
    f=pd.DataFrame(index=m.index);f['sin']=np.sin(2*np.pi*f.index.month/12);f['cos']=np.cos(2*np.pi*f.index.month/12)
    for col in ['precip_sum_mm','air_temp_mean_c','air_rh_mean_pct']:
        if group=='v1' and col!='precip_sum_mm':
            f[col+'_lag'+str(h+1)]=m[col].shift(h+1)
            continue
        lags=[h+1,h+2,h+3,12] if group=='v1' else [h+1,h+2,h+3,h+6,12,24]
        for lag in sorted(set(lags)):f[col+'_lag'+str(lag)]=m[col].shift(lag)
        if group=='expanded':
            for w in [3,6,12]:f[col+'_mean'+str(w)]=m[col].shift(h+1).rolling(w,min_periods=w).mean()
    features=list(f.columns)
    f['target_month']=f.index;f['origin_month']=f.index-pd.DateOffset(months=h)
    f['max_feature_month']=f.index-pd.DateOffset(months=h+1)
    return f,features

if __name__=='__main__':acquire();prepare()
