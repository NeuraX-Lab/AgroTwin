"""Real cached case plus explicitly synthetic rule/QA wiring tests."""
import copy
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from neurax.api import app
from neurax.agrotwin.inputs import AnalysisInput,Period,geometry_info
from neurax.agrotwin.data import load,acquire,qualify,numeric,daily_months
from neurax.agrotwin.engine import evaluate
from neurax.agrotwin.service import analyze


def request(**changes):
    value={'aoi_id':'MT-BLOCK-01','geometry':load('case.json')['geometry'],
           'period':{'start':'2025-01-01','end':'2026-01-01'},'farm':{},'source_mode':'offline'}
    value.update(changes)
    return AnalysisInput.model_validate(value)


def test_cached_real_data_dynamic_inputs_and_immutable_runs(tmp_path):
    original=request();a=analyze(original,tmp_path)
    assert a['a1']['status']=='partial' and a['a1']['data_as_of']=='2025-12-31'
    assert all(x['eligibility']=='needs_review' and x['score'] is None and x['is_current'] is None for x in a['a1']['results'])
    assert a['sidecar']['execution_mode']=='computed'
    saved=(tmp_path/'results'/f"{a['a1']['run_id']}.json").read_bytes()
    b=analyze(original,tmp_path)
    assert b['sidecar']['cache_hit'] and b['sidecar']['execution_mode']=='offline'
    assert a['a1']==b['a1']
    assert saved==(tmp_path/'results'/f"{a['a1']['run_id']}.json").read_bytes()
    changed=analyze(request(farm={'drainage_condition':'good'}),tmp_path)
    assert changed['a1']['run_id']!=a['a1']['run_id']
    assert changed['sidecar']['input_hash']!=a['sidecar']['input_hash']
    assert 'drainage_condition' not in changed['a1']['results'][1]['missing_inputs']
    assert all(x['score'] is None for x in changed['a1']['results'])


def test_other_geometry_does_not_receive_my_thanh_cache_or_references(tmp_path):
    geo=copy.deepcopy(load('case.json')['geometry'])
    for p in geo['features'][0]['geometry']['coordinates'][0]:p[0]+=.1
    a=analyze(request(aoi_id='area-B',geometry=geo),tmp_path)
    assert a['a1']['results']==[] and a['a1']['status']=='unavailable'
    assert a['source'] is None and a['soil_context'] is None
    assert all(x['rain'] is None for x in a['climate'])
    assert a['geometry']['geometry_hash']!=geometry_info(load('case.json')['geometry'])['geometry_hash']


def test_blank_zero_qa_fail_and_duplicate_months():
    assert numeric('') is None and numeric(None) is None and numeric(0)==0
    with pytest.raises(ValueError):numeric('NaN')
    period=Period(start='2025-01-01',end='2025-02-01')
    rows=qualify([{'date':'2025-01-01','rain':0,'temp':25,'coverage':1,'qa':'fail'}],period)
    assert rows[0]['qa']=='fail' and rows[0]['rain']==0
    with pytest.raises(ValueError,match='Duplicate'):qualify(rows+rows,period)
    with pytest.raises(ValueError,match='Negative'):qualify([{**rows[0],'rain':-1}],period)
    with pytest.raises(ValueError,match='Incomplete'):qualify([{**rows[0],'coverage':.5,'rain_coverage':.5}],period)


def test_draft_predicate_never_executes_and_verified_fixture_can_exclude(tmp_path):
    # SYNTHETIC predicate tests software only; it is not a production agronomic rule.
    req=request(farm={'drainage_condition':'poor'})
    data=acquire(req,tmp_path)
    catalog={'version':'SYNTHETIC','rotations':[{'id':'SYN','crops':['synthetic_a','synthetic_b']}],
             'rules':[{'id':'SYNTHETIC-ONLY','applies_to':['SYN'],'kind':'hard_constraint',
                       'required_inputs':['drainage_condition'],'source_ids':['SYNTHETIC-EVIDENCE'],
                       'statement':'Synthetic wiring fixture, not crop advice','approval_state':'draft',
                       'scope_aoi_ids':['MT-BLOCK-01'],'predicate':{'field':'drainage_condition','operator':'eq','value':'good'}}]}
    draft=evaluate(req,data,catalog)['a1']['results'][0]
    assert draft['eligibility']=='needs_review'
    rule=catalog['rules'][0];rule.update(approval_state='verified_applicable',reviewer='SYNTHETIC-REVIEWER',numeric_reviewer='SYNTHETIC-QA')
    verified=evaluate(req,data,catalog)['a1']['results'][0]
    assert verified['eligibility']=='ineligible' and verified['criteria'][1]['status']=='fail'
    rule['scope_aoi_ids']=['OTHER']
    assert evaluate(req,data,catalog)['a1']['results'][0]['eligibility']=='needs_review'


def test_source_fail_and_live_failure_do_not_become_pass(tmp_path):
    req=request(source_mode='live')
    with patch('neurax.agrotwin.data.fetch_power',side_effect=TimeoutError):
        data=acquire(req,tmp_path)
    assert data['source']['acquisition']=='versioned_cache' and data['warnings']
    data['months'][0]['qa']='fail'
    result=evaluate(req,data,load('catalog.json'))
    assert result['q1']['status']=='fail'
    assert all(x['eligibility']=='needs_review' for x in result['a1']['results'])


def test_geometry_and_api_contract(tmp_path,monkeypatch):
    monkeypatch.setenv('NEURAX_AGROTWIN_RUN_DIR',str(tmp_path))
    client=TestClient(app)
    a=client.post('/v1/analysis',json=request().model_dump(mode='json'))
    assert a.status_code==200 and a.json()['a1']['forecast'] is None
    assert client.get('/v1/analysis/runs/'+a.json()['a1']['run_id']).status_code==200
    assert client.get('/v1/analysis/runs/../../secret').status_code!=200
    bad=request().model_dump(mode='json');bad['geometry']['features'][0]['geometry']['coordinates'][0][1][0]=200
    assert client.post('/v1/analysis',json=bad).status_code==422
    assert 1.8<geometry_info(request().geometry)['area_ha']<2.2
    assert client.get('/v1/analysis/sources').status_code==200


def test_scientific_identity_across_independent_stores_and_acquisition_preferences(tmp_path):
    with patch('neurax.agrotwin.service.timestamp',return_value='2026-11-14T01:00:00Z'):
        a=analyze(request(),tmp_path/'first')
    with patch('neurax.agrotwin.service.timestamp',return_value='2026-11-15T01:00:00Z'):
        b=analyze(request(source_mode='prefer_cache'),tmp_path/'second')
    assert a['a1']['generated_at']!=b['a1']['generated_at']
    assert a['a1']['run_id']==b['a1']['run_id']
    assert a['sidecar']['scientific_payload_sha256']==b['sidecar']['scientific_payload_sha256']


def test_daily_partial_temperature_does_not_destroy_complete_precipitation():
    # SYNTHETIC transport/aggregation fixture; no agricultural conclusion.
    days={f'202501{i:02}':0 for i in range(1,32)}
    raw={'header':{'time_standard':'UTC'},'parameters':{'T2M':{'units':'C'},'PRECTOTCORR':{'units':'mm/day'}},
         'properties':{'parameter':{'T2M':{k:25 for k in days if k!='20250103'},'PRECTOTCORR':days}}}
    row=daily_months(raw,Period(start='2025-01-01',end='2025-02-01'))[0]
    assert row['rain']==0 and row['temp'] is None and row['qa']=='warn'
    assert row['rain_coverage']==1 and row['temp_coverage']<1
    raw['header']['time_standard']='LST'
    with pytest.raises(ValueError,match='UTC'):daily_months(raw,Period(start='2025-01-01',end='2025-02-01'))


def test_local_api_rejects_cross_site_and_oversized_input():
    client=TestClient(app)
    assert client.post('/v1/analysis',headers={'origin':'https://untrusted.example'},json={}).status_code==403
    assert client.post('/v1/analysis',content=b' '*131073).status_code==413


def test_complete_synthetic_reviewed_constraint_and_missing_rule_gate(tmp_path):
    req=request(farm={'current_crop':'SYNTHETIC','previous_crop':'SYNTHETIC','season':'SYNTHETIC',
                      'irrigation_access':'available','drainage_condition':'good'})
    data=acquire(req,tmp_path)
    catalog={'version':'SYNTHETIC-NOT-AGRONOMIC','rotations':[{'id':'SYN','crops':['synthetic']}],
             'rules':[{'id':'SYNTHETIC-ONLY','applies_to':['SYN'],'kind':'hard_constraint',
                       'required_inputs':['drainage_condition'],'source_ids':['SYNTHETIC-EVIDENCE'],
                       'statement':'Software gate only','approval_state':'verified_applicable',
                       'reviewer':'SYNTHETIC','numeric_reviewer':'SYNTHETIC','scope_aoi_ids':['MT-BLOCK-01'],
                       'predicate':{'field':'drainage_condition','operator':'eq','value':'good'}}]}
    eligible=evaluate(req,data,catalog)['a1']['results'][0]
    assert eligible['eligibility']=='eligible' and eligible['score'] is None
    catalog['rules']=[]
    result=evaluate(req,data,catalog)['a1']['results'][0]
    assert result['eligibility']=='needs_review' and 'applicable_reviewed_rule' in result['missing_inputs']
