"""Stable Dashboard adapter for the explicitly selected v4 system."""
from pathlib import Path
import sys,json,os,hashlib,uuid,logging
from contextlib import asynccontextmanager
from fastapi import FastAPI,HTTPException,Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from api_schemas import Analysis
from research_runtime import Engine
from research_rag import context_snapshot
import research_v3 as r
from research_v4 import EvidenceGate
from selected_v4_contract import AnalysisResponse

logger=logging.getLogger('uvicorn.error')
# Identify loaded code, not newly edited bytes that an old process never imported.
API_SHA256=r.sha(Path(__file__))
CONTRACT_SHA256=r.sha(ROOT/'scripts/selected_v4_contract.py')

class SelectedEngine(Engine):
    def __init__(self):
        config=json.loads((ROOT/'config/selected-system.json').read_text(encoding='utf-8'))
        if config['selected_system']!='v4' or config['auto_upgrade']:raise ValueError('Selected system must be pinned to v4')
        registry=ROOT/'runs/research-selected/artifact-manifest.json'
        if not registry.exists():raise FileNotFoundError('v4 artifact registry is required')
        entries=json.loads(registry.read_text(encoding='utf-8'))
        if len(entries['models'])!=6:raise ValueError('Expected six registered artifacts')
        if entries['ml_selection_sha256']!=r.sha(ROOT/'runs/research-v3/selection-frozen.json'):raise ValueError('ML selection checksum mismatch')
        if entries['rag_selection_sha256']!=r.sha(ROOT/'runs/research-v4-refined/selection-frozen.json'):raise ValueError('RAG selection checksum mismatch')
        for item in entries['models']:
            if r.sha(ROOT/item['path'])!=item['sha256']:raise ValueError('Artifact checksum mismatch')
        super().__init__(allow_version5=False)
        if not isinstance(self.rag,EvidenceGate) or len(self.models)!=6:raise ValueError('Expected six ML tasks and v4 evidence gate')
        for a in self.models.values():
            if a['meta']['dataset_sha256']!=r.sha(ROOT/'data/processed/v2/monthly.csv'):raise ValueError('Model/input dataset mismatch')
        self.provenance=dict(
            model_version='v3-climatology-rag-v4-pooled',selection_id=self.run_id,
            dataset_sha256=r.sha(ROOT/'data/processed/v2/monthly.csv'),
            corpus_sha256=r.sha(ROOT/'runs/research-v3/corpus-frozen.json'),
            ml_selection_sha256=entries['ml_selection_sha256'],rag_selection_sha256=entries['rag_selection_sha256'],
            models=[dict(task=x['task'],sha256=x['sha256']) for x in entries['models']])
    def analyze(self,*args,**kwargs):
        out=super().analyze(*args,**kwargs)
        out.update(selected_system='v4',api_schema_version='fieldshift-dashboard-1',blocks=dict(ML='v3 frozen climatology',RAG='v4 refined evidence gate',uncertainty='pooled'))
        request=dict(farm=args[0] if args else kwargs.get('farm',{}),question=args[1] if len(args)>1 else kwargs.get('question'))
        request_sha=hashlib.sha256(json.dumps(request,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        out.update(run_id='v4-'+uuid.uuid4().hex,question=request['question'],inference=dict(**self.provenance,execution_mode='fresh_model_inference',
            request_sha256=request_sha,prediction_count=len(out['forecasts']),cached=False))
        validated=AnalysisResponse.model_validate(out).model_dump(mode='json')
        logger.info('V4 inference run=%s request=%s models=6 selection=%s',validated['run_id'],request_sha,self.run_id)
        return validated

@asynccontextmanager
async def lifespan(app):
    try:app.state.engine=SelectedEngine();app.state.error=None
    except (OSError,ValueError,KeyError) as error:
        app.state.engine=None;app.state.error=type(error).__name__;logger.exception('Selected V4 artifacts unavailable')
    yield

app=FastAPI(title='FieldShift selected v4 Dashboard API',version='4.0.0',lifespan=lifespan)
origins=[x.strip() for x in os.getenv('FIELDSHIFT_DASHBOARD_ORIGINS','http://localhost:5174,http://127.0.0.1:5174,http://localhost:5173,http://127.0.0.1:5173,http://localhost:5180,http://127.0.0.1:5180,http://localhost:5179,http://127.0.0.1:5179,http://localhost:3000').split(',') if x.strip()]
app.add_middleware(CORSMiddleware,allow_origins=origins,allow_methods=['GET','POST','OPTIONS'],allow_headers=['Content-Type'],allow_credentials=False)

@app.middleware('http')
async def boundary(request:Request,call_next):
    origin=request.headers.get('origin')
    if origin and origin not in origins:return JSONResponse({'detail':'Origin not allowed'},status_code=403)
    try:size=int(request.headers.get('content-length','0'))
    except ValueError:return JSONResponse({'detail':'Invalid content length'},status_code=400)
    if size>16000:return JSONResponse({'detail':'Request too large'},status_code=413)
    return await call_next(request)

def engine():
    value=getattr(app.state,'engine',None)
    if value is None:raise HTTPException(503,dict(code='ARTIFACTS_UNAVAILABLE',message='Install the selected v4 runtime bundle and restart API'))
    return value

def envelope(**values):return dict(api_schema_version='fieldshift-dashboard-1',selected_system='v4',**values)

@app.get('/api/v4/status')
def status():
    e=engine();verified=sum(e.rag.source_valid(c) for c in e.rag.cards)
    return envelope(status='ready',run_id=e.run_id,region_id='MT-BLOCK-01',data_through=str(e.m.index.max().date()),research_only=True,domain_approved=False,
        service='agrotwin-selected-v4',runtime_root=str(ROOT),implementation_sha256=API_SHA256,contract_sha256=CONTRACT_SHA256,model_count=len(e.models),model_version=e.provenance['model_version'],
        evidence_sources=dict(status='ready' if verified==len(e.rag.cards) else 'partial',verified_cards=verified,total_cards=len(e.rag.cards)))
@app.get('/api/v4/forecasts')
def forecasts():return envelope(forecasts=engine().forecasts())
@app.get('/api/v4/overview')
def overview():
    e=engine();m=e.m.tail(24)
    return envelope(run_id=e.run_id,forecasts=e.forecasts(),context=context_snapshot(),
        months=[dict(date=str(d.date()),rain=float(row.precip_sum_mm),temp=float(row.air_temp_mean_c),rh=float(row.air_rh_mean_pct)) for d,row in m.iterrows()],
        decision=e.analyze({})['decision'],data_through=str(e.m.index.max().date()),warnings=['Single-AOI gridded estimates; no field-trial accuracy or achieved 80% coverage guarantee'])
@app.post('/api/v4/analyze',response_model=AnalysisResponse)
def analyze(body:Analysis):
    try:return engine().analyze(body.farm.model_dump(mode='json',exclude_none=True),body.question)
    except (OSError,ValueError,KeyError,TypeError) as error:
        logger.exception('V4 inference failed')
        raise HTTPException(503,dict(code='INFERENCE_UNAVAILABLE',message='Selected V4 inference failed validation; inspect local API log')) from error
@app.get('/api/v4/evidence')
def evidence():return envelope(cards=engine().rag.cards)
@app.get('/api/v4/metrics')
def metrics():
    engine()
    return envelope(ML=json.loads((ROOT/'reports/v3/evidence/final-diagnostic.json').read_text(encoding='utf-8')),
        RAG=json.loads((ROOT/'reports/v4/evidence/refined/final.json').read_text(encoding='utf-8'))['selected']['metrics'],independent_test=False)
