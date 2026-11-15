from pathlib import Path
import sys,json
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from selected_v4_api import app,SelectedEngine

def test_selected_v4_never_uses_later_intervals():
    e=SelectedEngine();assert e.band_override is None
    result=e.analyze({},'T2M là gì?')
    assert result['selected_system']=='v4' and result['blocks']['uncertainty']=='pooled'
    assert result['rag']['source_bytes_verified']

def test_dashboard_contract_and_cors():
    with TestClient(app) as c:
        for endpoint in ['status','forecasts','overview','metrics','evidence']:
            a=c.get('/api/v4/'+endpoint);assert a.status_code==200 and a.json()['selected_system']=='v4'
        assert len(c.get('/api/v4/forecasts').json()['forecasts'])==6
        a=c.options('/api/v4/analyze',headers={'Origin':'http://localhost:5173','Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'content-type'})
        assert a.status_code==200 and a.headers['access-control-allow-origin']=='http://localhost:5173'
        assert c.post('/api/v4/analyze',json={'farm':{'soil_ph':20}}).status_code==422
        assert c.post('/api/v4/analyze',json={},headers={'Origin':'https://unknown.example'}).status_code==403
        a=c.post('/api/v4/analyze',json={'farm':{'drainage':'poor'},'question':'What is field EC at this plot?'})
        assert a.json()['rag']['status']=='insufficient_evidence'
        assert {x['crop'] for x in a.json()['decision']['options'] if x['status']=='blocked'}=={'mungbean','baby_corn'}

def test_missing_artifacts_produces_explicit_unavailable():
    with TestClient(app) as c:
        app.state.engine=None
        assert c.get('/api/v4/status').status_code==503
