from pathlib import Path
import copy
import json
import sys
import pytest
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from research_v4 import EvidenceGate,OUT
from research_runtime import Engine,Forecast,app
import research_v3 as r


def gate():
    s=json.loads((OUT/'selection-frozen.json').read_text(encoding='utf-8'))
    return EvidenceGate(s['selected']['threshold'])


def test_unrelated_crop_question_is_not_supported_by_generic_rice_match():
    for q in ['Rice protein content per 100 grams?','Wheat irrigation requirements?']:
        a=gate().answer(q)
        assert a['status']=='insufficient_evidence' and not a['citations']


def test_same_size_wrong_source_bytes_are_detected(tmp_path):
    rag=gate();card=next(c for c in rag.cards if c['id']=='mungbean-water')
    bad=tmp_path/'substituted-source';bad.write_bytes(b'Wrong source, no actual raw file touched')
    rag.paths[card['source']['sha256']]=bad
    assert rag.answer('Does mungbean need irrigation and drainage?')['abstention_reason']=='source_integrity_failure'


def test_changed_source_after_first_answer_is_not_hidden_by_cache(tmp_path):
    rag=gate();card=next(c for c in rag.cards if c['id']=='mungbean-water')
    source=rag.paths[card['source']['sha256']];local=tmp_path/'copy';local.write_bytes(source.read_bytes())
    rag.paths[card['source']['sha256']]=local
    assert rag.answer('Does mungbean need irrigation and drainage?')['source_bytes_verified']
    local.write_bytes(b'corrupted')
    assert rag.answer('Does mungbean need irrigation and drainage?')['status']=='insufficient_evidence'


def test_block_interface_rejects_unit_region_dates_nonfinite_and_wrong_bounds():
    good=Engine().forecasts()[0]
    for field,value in [('unit','degC' if good['unit']!='degC' else 'percent'),('region_id','elsewhere'),
                        ('value',float('nan')),('lower',good['upper']+10),('origin_month','1900-01-01')]:
        bad=dict(good);bad[field]=value
        with pytest.raises(ValueError):Forecast.model_validate(bad)


def test_forecast_error_or_missing_cannot_promote_crop_options():
    engine=Engine();farm={'drainage':'poor','saline':True}
    normal=engine.forecasts();perturbed=copy.deepcopy(normal)
    for x in perturbed:
        if x['target']=='precip_sum_mm':x.update(value=100000,lower=0,upper=200000)
    a=engine.analyze(farm,forecasts=normal);b=engine.analyze(farm,forecasts=perturbed);c=engine.analyze(farm,forecasts=[])
    assert a['decision']['options']==b['decision']['options']==c['decision']['options']
    assert c['decision']['climate_context'] is None and c['warnings']


def test_outside_window_forecast_and_invalid_ml_are_isolated():
    e=Engine();farm={'window_start':'2028-01-01','window_end':'2028-04-01'}
    a=e.analyze(farm);assert a['decision']['climate_context'] is None and a['warnings']
    bad=e.forecasts()[0];bad['unit']='wrong'
    a=e.analyze({},forecasts=[bad]);assert not a['forecasts'] and a['warnings']


def test_api_compatible_alias_and_input_validation():
    client=TestClient(app)
    assert client.get('/api/research/forecasts').status_code==200
    assert len(client.get('/api/research/forecasts').json()['forecasts'])==6
    a=client.post('/api/v2/analyze',json={'farm':{},'question':'T2M là gì?'})
    assert a.status_code==200 and a.json()['schema_version']=='fieldshift-2'
    assert a.json()['rag']['source_bytes_verified']
    assert client.post('/api/research/analyze',json={'farm':{'soil_ph':15}}).status_code==422
    assert client.post('/api/research/analyze',json={'region_id':'elsewhere'}).status_code==422
    assert client.post('/api/research/analyze',json={},headers={'Origin':'https://foreign.example'}).status_code==403


def test_runtime_rejects_changed_ml_input_without_touching_raw(monkeypatch):
    original=r.sha
    def substituted(path):
        return '0'*64 if Path(path)==ROOT/'data/processed/v2/monthly.csv' else original(path)
    monkeypatch.setattr(r,'sha',substituted)
    with pytest.raises(ValueError,match='ML input checksum'):Engine()
