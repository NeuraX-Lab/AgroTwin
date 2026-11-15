import copy
import json
from datetime import datetime,timezone,timedelta
import numpy as np
import pytest
from fastapi.testclient import TestClient
from neurax.api import app
from neurax.agrotwin.research import experiment,production_inference_gate
from neurax.agrotwin.data import load
from neurax.agrotwin.h1 import Event,Batch,summarize,ingest
from neurax.train import _features


def test_lags_never_read_target_or_future():
    import pandas as pd
    values=np.arange(48,dtype=float);dates=list(pd.date_range('2020-01-01',periods=48,freq='MS'))
    first=_features(values,dates);values[30:]=999
    np.testing.assert_array_equal(first[:19],_features(values,dates)[:19])


def test_final_labels_cannot_change_model_selection(tmp_path):
    # Real cache used for protocol regression; perturbed final labels are TEST_ONLY.
    rows=load('climate.json')['months']
    (tmp_path/'one').mkdir();(tmp_path/'two').mkdir()
    a=experiment(rows,tmp_path/'one');changed=copy.deepcopy(rows)
    for r in changed:
        if r['date']>='2024-01-01':r['temp']+=10
    b=experiment(changed,tmp_path/'two')
    assert a['selection']==b['selection'] and a['final_e1']!=b['final_e1']
    assert a['artifact_sha256']==b['artifact_sha256']
    assert a['final_holdout_n']==24 and a['train_final_n']==96
    with pytest.raises(ValueError,match='production'):production_inference_gate(a)


def event(**updates):
    data=dict(device_id='TEST_ONLY',event_type='air_temperature',timestamp_utc=datetime(2026,11,14,0,0,tzinfo=timezone.utc),
              value=0,unit='°C',quality='pass',data_mode='observed',delivery_mode='live',calibration_id='TEST-CAL',source_context='TEST_ONLY bench')
    data.update(updates);return Event(**data)


def test_h1_zero_dedup_clock_units_and_bench_exclusion(tmp_path):
    now=event().timestamp_utc
    e=event();a=summarize([e,e],now)
    assert a['duplicates']==1 and a['features'][0]['mean']==0 and not a['features'][0]['eligible_for_A1']
    conflict=summarize([event(event_id='TEST_ID'),event(event_id='TEST_ID',value=1)],now)
    assert conflict['conflicting_duplicates']==1 and 'conflicting_duplicate' in conflict['features'][0]['flags']
    bad=summarize([event(timestamp_utc=now+timedelta(seconds=60),unit='unknown')],now)['features'][0]
    assert 'future_clock' in bad['flags'] and 'unit_or_quantity_unverified' in bad['flags'] and bad['mean'] is None
    batch=Batch(events=[e]);first=ingest(batch,tmp_path);path=tmp_path/'h1'/(first['batch_sha256']+'.json');saved=path.read_bytes()
    assert ingest(batch,tmp_path)['duplicate_batch'] and path.read_bytes()==saved
    with pytest.raises(ValueError):event(value=float('nan'))
    with pytest.raises(ValueError):event(timestamp_utc=now.replace(tzinfo=None))


def test_only_trusted_field_registry_can_make_monitoring_features_eligible():
    now=event().timestamp_utc
    events=[event(timestamp_utc=now-timedelta(seconds=5*i)) for i in range(61)]
    registry={'TEST_ONLY':{'field_verified':True,'verified_by':'TEST_ONLY','aoi_id':'TEST_AOI','calibration_id':'TEST-CAL','applicable_K1':['TEST_ONLY']}}
    a=summarize(events,now,registry)['features'][0];assert a['coverage']==1 and a['eligible_for_A1']
    for e in events:e.data_mode='simulated'
    assert not summarize(events,now,registry)['features'][0]['eligible_for_A1']


def test_ingest_api_rejects_client_approval_and_cross_site(tmp_path,monkeypatch):
    monkeypatch.setenv('NEURAX_AGROTWIN_RUN_DIR',str(tmp_path));c=TestClient(app)
    payload={'events':[event().model_dump(mode='json')]}
    r=c.post('/v1/h1/ingest',json=payload);assert r.status_code==200
    assert all(not f['eligible_for_A1'] for f in r.json()['features'])
    assert c.post('/v1/h1/ingest',json={**payload,'field_verified':True}).status_code==422
    assert c.post('/v1/h1/ingest',json=payload,headers={'origin':'https://example.com'}).status_code==403


def test_legacy_forecast_http_route_cannot_bypass_research_gate(tmp_path,monkeypatch):
    monkeypatch.setenv('NEURAX_RUN_DIR',str(tmp_path))
    (tmp_path/'forecast').mkdir()
    (tmp_path/'forecast/forecast_metadata.json').write_text(json.dumps({'selection':'candidate','production_approved':False}))
    assert TestClient(app).get('/v1/forecast/next').status_code==409
