"""Local FastAPI shell for read-only reports and a trained rainfall forecast.

Bind to 127.0.0.1 unless operators explicitly configure auth, HTTPS, network rules.
"""
from __future__ import annotations
import json, os
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from urllib.parse import urlsplit
from pydantic import BaseModel, Field
from .agrotwin.inputs import AnalysisInput
from .agrotwin.service import analyze as analyze_agrotwin,read_run
from .agrotwin.data import load as load_agrotwin_resource
from .agrotwin.h1 import Batch as H1Batch,ingest as ingest_h1

app=FastAPI(title='NeuraX Local Research API',version='0.2.0',
            description='Evidence-gated reports and forecast. Not a crop management service.')

def agrotwin_store():
    return Path(os.environ.get('NEURAX_AGROTWIN_RUN_DIR','runs/agrotwin')).resolve()

@app.middleware('http')
async def analysis_input_boundary(request:Request,call_next):
    if request.method=='POST' and request.url.path in ('/v1/analysis','/v1/h1/ingest'):
        origin=request.headers.get('origin')
        if origin and urlsplit(origin).hostname not in ('localhost','127.0.0.1'):
            return JSONResponse({'detail':'Local development API; cross-site requests are not allowed'},status_code=403)
        if len(await request.body())>131072:
            return JSONResponse({'detail':'Analysis request exceeds 128 KB'},status_code=413)
    return await call_next(request)

@app.post('/v1/analysis')
def agrotwin_analysis(body:AnalysisInput):
    try:return analyze_agrotwin(body,agrotwin_store())
    except ValueError as ex:raise HTTPException(status_code=422,detail=str(ex))

@app.get('/v1/analysis/runs/{run_id}')
def agrotwin_run(run_id:str):
    try:return read_run(run_id,agrotwin_store())
    except ValueError:raise HTTPException(status_code=422,detail='Invalid run ID')
    except FileNotFoundError:raise HTTPException(status_code=404,detail='Run not found')

@app.get('/v1/analysis/sources')
def agrotwin_sources():return load_agrotwin_resource('sources.json')

@app.post('/v1/h1/ingest')
def h1_ingest(body:H1Batch):return ingest_h1(body,agrotwin_store())

def run_path()->Path:
    return Path(os.environ.get('NEURAX_RUN_DIR','runs/latest')).resolve()

def _read(name):
    f=run_path()/name
    if not f.exists():raise HTTPException(status_code=404,detail=f'No {name}; run analyze or train first')
    try:return json.loads(f.read_text(encoding='utf-8'))
    except ValueError:raise HTTPException(status_code=500,detail='Invalid local artifact')

@app.get('/v1/status')
def status():
    return {'state':'local_research_api','dataset_loaded':(run_path()/'inventory.json').exists(),
            'forecast_available':(run_path()/'forecast'/'forecast_metadata.json').exists(),
            'run_dir':str(run_path()),'live_hardware':False, 'ai_review_available':(run_path()/'decision.json').exists()}

@app.get('/v1/reports/inventory')
def inventory():return _read('inventory.json')

@app.get('/v1/reports/fit')
def fit():return _read('fit.json')

@app.get('/v1/reports/model-plan')
def model_plan():return _read('model_plan.json')

@app.get('/v1/reports/research')
def research_queue():return _read('research_queue.json')

@app.get('/v1/reports/ai-decision')
def ai_decision():return _read('decision.json')

@app.get('/v1/reports/ai-evidence')
def ai_evidence():return _read('evidence_ledger.json')

@app.get('/v1/forecast/next')
def forecast():
    folder=run_path()/'forecast'
    if not (folder/'forecast_metadata.json').is_file():
        raise HTTPException(status_code=404,detail='Forecast not trained. No default prediction invented.')
    # The legacy CLI can emit research forecasts, but its selection holdout is not
    # production approval. No approved inference consumer exists in V4.1.
    raise HTTPException(status_code=409,detail='Research-only artifact: production inference is not approved. Use the offline CLI/report for research evidence.')

class DeviceEvent(BaseModel):
    device_id:str=Field(min_length=1,max_length=64)
    event_type:str=Field(min_length=1,max_length=64)
    timestamp_utc:str=Field(min_length=15,max_length=40)
    value:float|None=None
    unit:str|None=Field(default=None,max_length=40)
    quality:str=Field(default='unverified',max_length=30)
    data_mode:str=Field(default='simulated',pattern='^(simulated|observed|replay)$')

@app.post('/v1/hardware/validate')
def validate_hardware(event:DeviceEvent):
    # Does not write to database, and does NOT assert that 'observed' is verified.
    return {'valid_shape':True,'storage':'none','event':event.model_dump(),
            'warning':'Schema validation only; not an electrical calibration or evidence of live data.'}
