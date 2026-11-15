"""Public demo adapter: the same selected v4, same-origin API, ephemeral A1/H1."""
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
import sys

ROOT = Path(__file__).resolve().parent
for folder in ['backend','backend/scripts','a1']:
    sys.path.insert(0,str(ROOT/folder))

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from scripts import selected_v4_api as selected
from neurax.agrotwin.inputs import AnalysisInput
from neurax.agrotwin.service import analyze as analyze_a1
from neurax.agrotwin.data import load
from neurax.agrotwin.h1 import Batch, ingest

@asynccontextmanager
async def lifespan(_app):
    async with selected.lifespan(selected.app):
        if selected.app.state.engine is None:
            raise RuntimeError('Selected v4 frozen resources are unavailable')
        yield

app = FastAPI(title='AgroTwin public research demo',version='4.0.0',lifespan=lifespan,
              docs_url=None,redoc_url=None,openapi_url=None)

@app.middleware('http')
async def demo_boundary(request: Request, call_next):
    if request.url.path.startswith('/api/'):
        origin = request.headers.get('origin')
        if origin:
            parsed = urlsplit(origin)
            expected_host = request.headers.get('host','').lower()
            expected_scheme = 'http' if expected_host.split(':')[0] in {'localhost','127.0.0.1','testserver'} else 'https'
            if parsed.netloc.lower() != expected_host or parsed.scheme != expected_scheme:
                return JSONResponse({'detail':'Same-origin demo requests only'},status_code=403)
        if request.method == 'POST':
            limit = 16000 if request.url.path.startswith('/api/v4/') else 131072
            try: declared = int(request.headers.get('content-length','0'))
            except ValueError: return JSONResponse({'detail':'Invalid content length'},status_code=400)
            if declared < 0:
                return JSONResponse({'detail':'Invalid content length'},status_code=400)
            if declared > limit or len(await request.body()) > limit:
                return JSONResponse({'detail':'Request too large'},status_code=413)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response

# Reuse the selected endpoints and contracts; the public adapter supplies its
# own same-origin boundary. The local-only original apps stay unchanged.
for route in selected.app.routes:
    if isinstance(route,APIRoute) and route.path.startswith('/api/v4/'):
        app.router.routes.append(route)

@app.get('/api/health')
def health():
    engine = selected.engine()
    return dict(status='ready',selected_system='v4',models=len(engine.models),
                evidence_verified=sum(engine.rag.source_valid(c) for c in engine.rag.cards),
                evidence_total=len(engine.rag.cards),research_only=True)

@app.get('/api/v1/status')
def a1_status():
    return dict(state='public_research_demo',dataset_loaded=True,forecast_available=False,
                live_hardware=False,storage='request_scoped_temporary')

@app.get('/api/v1/analysis/sources')
def sources(): return load('sources.json')

@app.post('/api/v1/analysis')
def analysis(body: AnalysisInput):
    # Results are saved by the browser. Public submissions are not retained in a
    # shared server history or written to the read-only function source tree.
    try:
        with TemporaryDirectory(prefix='agrotwin-a1-') as directory:
            return analyze_a1(body,Path(directory))
    except ValueError as error: raise HTTPException(422,str(error)) from error

@app.post('/api/v1/h1/ingest')
def hardware(body: Batch):
    with TemporaryDirectory(prefix='agrotwin-h1-') as directory:
        result = ingest(body,Path(directory))
    result['deployment_storage'] = 'request_scoped_temporary; no cross-request history or field calibration'
    return result

@app.get('/api/{unknown:path}',include_in_schema=False)
def unavailable(unknown: str):
    raise HTTPException(404,'This endpoint is not part of the selected v4 public demo')

# CDN promotion serves only the curated frontend build. Backend resources and
# publisher publications are never mounted or made available as static files.
app.frontend('/',directory=str(ROOT/'frontend/dist'),fallback='index.html',check_dir=False)
