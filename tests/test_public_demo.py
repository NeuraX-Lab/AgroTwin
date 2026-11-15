"""Exercise the deployed adapter, not a substitute forecast or mocked API."""
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
import pytest
import main

@pytest.fixture
def client():
    with TestClient(main.app,base_url='https://demo.example') as value: yield value

def test_public_health_and_fresh_selected_inference(client):
    status=client.get('/api/health').json()
    assert status['selected_system']=='v4' and status['models']==6
    result=client.post('/api/v4/analyze',json={'farm':{'drainage':'poor'},'question':'T2M là gì?'},headers={'Origin':'https://demo.example'})
    assert result.status_code==200
    body=result.json()
    assert len(body['forecasts'])==6 and body['inference']['cached'] is False
    assert body['rag']['source_bytes_verified']
    assert result.headers['cache-control']=='no-store'

def test_cross_origin_and_over_limit_requests_are_rejected(client):
    assert client.post('/api/v4/analyze',json={},headers={'Origin':'https://unrelated.example'}).status_code==403
    assert client.post('/api/v4/analyze',content='x'*16001).status_code==413
    assert client.post('/api/v1/analysis',content='x'*131073).status_code==413

def test_a1_executes_with_request_scoped_storage(client):
    stores=[]
    original=main.analyze_a1
    def observed(body,store):
        assert store.is_dir();stores.append(store)
        return original(body,store)
    request=dict(aoi_id='MT-BLOCK-01',geometry=main.load('case.json')['geometry'],
                 period={'start':'2025-01-01','end':'2026-01-01'},farm={},source_mode='offline')
    with patch.object(main,'analyze_a1',side_effect=observed):
        response=client.post('/api/v1/analysis',json=request,headers={'Origin':'https://demo.example'})
    assert response.status_code==200 and response.json()['a1']['run_id'].startswith('a1-')
    assert stores and all(not store.exists() for store in stores)

def test_api_misses_do_not_become_frontend_or_publisher_downloads(client):
    response=client.get('/api/not-a-real-endpoint')
    assert response.status_code==404 and response.headers['content-type'].startswith('application/json')
    assert client.get('/api/v1/analysis/runs/a1-'+'0'*24).status_code==404
    if (main.ROOT/'frontend/dist').is_dir():
        response=client.get('/backend/data/raw/v2/agronomy/DROUGHT2026.pdf')
        assert response.status_code==404 or 'application/pdf' not in response.headers.get('content-type','')
