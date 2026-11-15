"""Block A/B contract, saved inference and local research API.

Run: python -m uvicorn scripts.research_runtime:app --host 127.0.0.1 --port 8183
"""
from pathlib import Path
from datetime import date
from typing import Literal
import json
import sys
import time
import numpy as np
import pandas as pd
from joblib import load
from pydantic import BaseModel, ConfigDict, model_validator
from fastapi import FastAPI
from fastapi.responses import JSONResponse
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import research_v3 as r
import research_v4 as rag
from v2_runtime import rules
from api_schemas import Analysis


class Forecast(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    target:Literal['precip_sum_mm','air_temp_mean_c','air_rh_mean_pct']
    horizon_months:Literal[1,3]
    region_id:Literal['MT-BLOCK-01']='MT-BLOCK-01'
    unit:Literal['mm/month','degC','percent']
    target_month:date
    data_through:date
    origin_month:date
    value:float
    lower:float
    upper:float
    nominal_coverage:float=.8
    coverage_guaranteed:Literal[False]=False
    method:str
    historical_vintage_verified:bool=False
    uncertainty_method:str='held-separate empirical calibration'

    @model_validator(mode='after')
    def validate_semantics(self):
        if self.unit!=r.P['targets'][self.target]:raise ValueError('Target/unit mismatch')
        if not self.lower<=self.value<=self.upper:raise ValueError('Invalid uncertainty bounds')
        if self.target in ['precip_sum_mm','air_rh_mean_pct'] and self.lower<0:raise ValueError('Negative rain/RH')
        if self.target=='air_rh_mean_pct' and self.upper>100:raise ValueError('RH exceeds 100 percent')
        if any(x.day!=1 for x in [self.target_month,self.data_through,self.origin_month]):raise ValueError('Calendar month starts required')
        expected=pd.Timestamp(self.target_month)-pd.DateOffset(months=self.horizon_months)
        if expected!=pd.Timestamp(self.origin_month):raise ValueError('Horizon/origin mismatch')
        if pd.Timestamp(self.data_through)>expected-pd.DateOffset(months=1):raise ValueError('Unavailable observation at origin')
        if self.nominal_coverage!=.8:raise ValueError('Only 80 percent calibration is supported')
        return self


class Engine:
    def __init__(self,allow_version5=True):
        ledger=json.loads((r.OUT/'selection-frozen.json').read_text(encoding='utf-8'))
        manifest=json.loads((r.OUT/'data-manifest.json').read_text(encoding='utf-8'))
        weather=ROOT/'data/processed/v2/monthly.csv'
        pinned=next(x for x in manifest['files'] if x['path']=='data/processed/v2/monthly.csv')
        if r.sha(weather)!=pinned['sha256']:raise ValueError('Frozen ML input checksum mismatch')
        self.m=r.data();self.models={};self.tasks=ledger['tasks']
        registry=ROOT/'runs/research-selected/artifact-manifest.json'
        hashes={x['path']:x['sha256'] for x in json.loads(registry.read_text(encoding='utf-8'))['models']} if registry.exists() else {}
        for key in self.tasks:
            path=r.OUT/key/'model.joblib';expected=hashes.get(path.relative_to(ROOT).as_posix())
            if expected and r.sha(path)!=expected:raise ValueError('Saved model checksum mismatch')
            self.models[key]=load(path)
        selection=json.loads((rag.OUT/'selection-frozen.json').read_text(encoding='utf-8'))
        self.rag=rag.EvidenceGate(selection['selected']['threshold']) if selection['promoted'] else rag.RAG()
        self.run_id='research-'+r.sha(r.OUT/'selection-frozen.json')[:12]
        self.band_override=None
        selected_bands=ROOT/'runs/research-v5/bands-frozen.json'
        selection_path=ROOT/'runs/research-v5/selection-frozen.json'
        if allow_version5 and selected_bands.exists() and selection_path.exists() and json.loads(selection_path.read_text(encoding='utf-8'))['promoted']:
            self.band_override=json.loads(selected_bands.read_text(encoding='utf-8'))

    def forecasts(self):
        out=[]
        for key,a in self.models.items():
            t=self.tasks[key];h=t['h'];target=self.m.index.max()+pd.DateOffset(months=h+1)
            full=self.m.reindex(pd.date_range(self.m.index.min(),target,freq='MS'))
            value=float(r.predict(a,full,pd.DatetimeIndex([target]))[0]);radius=a['meta']['radius']
            if self.band_override:
                b=self.band_override[key];season='dry' if target.month in [12,1,2,3,4] else 'wet';radius=b.get(season,b['pooled'])
            out.append(Forecast(target=t['target'],horizon_months=h,unit=r.P['targets'][t['target']],target_month=target.date(),
                                data_through=self.m.index.max().date(),origin_month=(target-pd.DateOffset(months=h)).date(),
                                value=value,lower=float(r.clip([value-radius],t['target'])[0]),upper=float(r.clip([value+radius],t['target'])[0]),
                                method=t['spec']['id'],uncertainty_method='v5 frozen empirical bands' if self.band_override else 'v3 pooled empirical bands').model_dump(mode='json'))
        return out

    def analyze(self,farm,question=None,forecasts=None):
        start=time.perf_counter();valid=[];warnings=['Empirical nominal 80% intervals have no coverage guarantee under temporal shift; research use only']
        incoming=self.forecasts() if forecasts is None else forecasts
        seen=set()
        for item in incoming:
            try:
                f=Forecast.model_validate(item);key=(f.target,f.horizon_months)
                if key in seen:raise ValueError('Duplicate target/horizon')
                seen.add(key);valid.append(f.model_dump(mode='json'))
            except (ValueError,TypeError) as exc:warnings.append('ML output excluded: '+str(exc).splitlines()[0])
        if len(valid)<6:warnings.append('Incomplete ML block; missing forecasts do not establish crop suitability')
        # Missing or poor weather predictions must never manufacture crop
        # eligibility. Only self-reported farm conditions drive constraint checks.
        compatible=valid
        if farm.get('window_start') and farm.get('window_end'):
            compatible=[f for f in valid if str(farm['window_start'])[:7]<=f['target_month'][:7]<=str(farm['window_end'])[:7]]
            if len(compatible)<len(valid):warnings.append('Forecast outside planting window omitted from decision context')
        result=dict(schema_version='fieldshift-2',research_schema_version='fieldshift-research-1',run_id=self.run_id,status='research_only',
                    region_id='MT-BLOCK-01',generated_at_utc=pd.Timestamp.now(tz='UTC').isoformat(),forecasts=valid,decision=rules(farm,compatible),rag=self.rag.answer(question) if question else None,
                    warnings=warnings,input_origin='self_reported_unverified',domain_approved=False,
                    blocks=dict(ML='v3 frozen selection',RAG='v4 evidence gate',uncertainty='v5' if self.band_override else 'v3'),
                    latency_ms=(time.perf_counter()-start)*1000)
        return result


app=FastAPI(title='FieldShift frozen-data research',version='3-5')
_engine=None


def engine():
    global _engine
    if _engine is None:_engine=Engine()
    return _engine


@app.middleware('http')
async def local_boundary(request,call_next):
    if request.headers.get('origin') and request.headers['origin'] not in ['http://127.0.0.1:8183','http://localhost:8183']:
        return JSONResponse({'detail':'Foreign Origin rejected'},status_code=403)
    try:size=int(request.headers.get('content-length','0'))
    except ValueError:return JSONResponse({'detail':'Invalid content length'},status_code=400)
    if size>16000:return JSONResponse({'detail':'Request too large'},status_code=413)
    return await call_next(request)


@app.get('/api/research/status')
def status():return dict(status='ok',schema_version='fieldshift-research-1',scope='single-AOI retrospective research')


@app.get('/api/research/forecasts')
def forecasts():return dict(schema_version='fieldshift-research-1',forecasts=engine().forecasts())


@app.post('/api/research/analyze')
@app.post('/api/v2/analyze')
def analyze(body:Analysis):return engine().analyze(body.farm.model_dump(mode='json',exclude_none=True),body.question)
