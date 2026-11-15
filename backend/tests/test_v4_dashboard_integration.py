"""New-session integration checks; no training or fabricated forecasts."""
import copy
import sys
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from selected_v4_api import SelectedEngine, app
from selected_v4_contract import AnalysisResponse
import research_v3 as research


def test_each_analysis_executes_six_predictions_and_has_immutable_identity():
    e = SelectedEngine()
    with patch.object(research, 'predict', wraps=research.predict) as predict:
        a = e.analyze({'drainage': 'poor'}, 'T2M là gì?')
        b = e.analyze({'drainage': 'good'}, 'What is field EC at this plot?')
        assert predict.call_count == 12
    assert a['run_id'] != b['run_id']
    assert a['inference']['selection_id'] == b['inference']['selection_id'] == e.run_id
    assert a['inference']['request_sha256'] != b['inference']['request_sha256']
    assert a['inference']['cached'] is False
    assert a['question'] == 'T2M là gì?' and b['question'] == 'What is field EC at this plot?'
    assert a['rag']['source_bytes_verified'] and a['rag']['citations'][0]['sha256']
    assert b['rag']['status'] == 'insufficient_evidence' and b['rag']['citations'] == []
    assert {o['id'] for o in a['decision']['options'] if o['status'] == 'blocked'} == {'R1', 'R2'}
    assert all(o['status'] == 'needs_information' for o in b['decision']['options'])
    assert all(f['method'] == 'clim-mean' and f['uncertainty_method'] == 'v3 pooled empirical bands' for f in a['forecasts'])


def test_output_contract_rejects_scientific_corruption():
    out = SelectedEngine().analyze({}, 'T2M là gì?')
    for mutate in [
        lambda a: a['forecasts'][0].update(unit='degC'),
        lambda a: a['forecasts'][0].update(origin_month='2026-10-01'),
        lambda a: a['forecasts'][0].update(lower=a['forecasts'][0]['value'] + 1),
        lambda a: a['decision']['options'][0].update(score=1),
        lambda a: a['rag'].update(source_bytes_verified=False),
    ]:
        bad = copy.deepcopy(out)
        mutate(bad)
        with pytest.raises(ValueError):
            AnalysisResponse.model_validate(bad)


def test_dashboard_port_errors_and_corrupt_inference():
    with TestClient(app) as client:
        s = client.get('/api/v4/status').json()
        assert s['model_count'] == 6 and s['service'] == 'agrotwin-selected-v4'
        expected = sum(app.state.engine.rag.source_valid(card) for card in app.state.engine.rag.cards)
        assert s['evidence_sources']['total_cards'] == 17
        assert s['evidence_sources']['verified_cards'] == expected
        assert s['evidence_sources']['status'] == ('ready' if expected == 17 else 'partial')
        with patch.object(research, 'sha', return_value='0' * 64):
            loaded = client.get('/api/v4/status').json()
            assert loaded['implementation_sha256'] == s['implementation_sha256']
            assert loaded['contract_sha256'] == s['contract_sha256']
        response = client.options('/api/v4/analyze', headers={
            'Origin': 'http://127.0.0.1:5174', 'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'content-type'})
        assert response.headers['access-control-allow-origin'] == 'http://127.0.0.1:5174'
        for request in [{'region_id': 'OTHER'}, {'farm': {'unexpected': 1}},
                        {'farm': {'window_start': '2027-02-01', 'window_end': '2026-12-01'}},
                        {'farm': {'soil_ph': 20}}, {'question': ''}]:
            assert client.post('/api/v4/analyze', json=request).status_code == 422
        assert client.post('/api/v4/analyze', content='x' * 16001).status_code == 413
        with patch.object(app.state.engine, 'forecasts', return_value=[]):
            result = client.post('/api/v4/analyze', json={})
            assert result.status_code == 503
            assert result.json()['detail']['code'] == 'INFERENCE_UNAVAILABLE'


def test_selected_registry_hash_failure_is_not_silent(monkeypatch):
    original = research.sha
    monkeypatch.setattr(research, 'sha', lambda p: '0' * 64 if str(p).endswith('model.joblib') else original(p))
    with pytest.raises(ValueError, match='checksum'):
        SelectedEngine()


def test_missing_publications_are_reported_and_cannot_support_answers():
    with TestClient(app) as client:
        with patch.object(app.state.engine.rag, 'paths', {}):
            status = client.get('/api/v4/status').json()
            assert status['evidence_sources'] == dict(status='partial', verified_cards=0, total_cards=17)
            response = client.post('/api/v4/analyze', json={'farm': {}, 'question': 'T2M là gì?'}).json()
            assert response['rag']['status'] == 'insufficient_evidence'
            assert response['rag']['citations'] == []
            assert response['rag']['source_bytes_verified'] is False
