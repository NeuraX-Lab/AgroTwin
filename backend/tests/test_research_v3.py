"""Independent causality, source aggregation and frozen-selection contracts."""
from pathlib import Path
import sys
import json
import numpy as np
import pandas as pd
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import research_v3 as r


@pytest.mark.parametrize('h',[1,3])
def test_unavailable_labels_cannot_change_fit_or_forecast(h):
    m=r.data();date=pd.Timestamp('2008-06-01');cutoff=date-pd.DateOffset(months=h+1)
    changed=m.copy();changed.loc[changed.index>cutoff,list(r.P['targets'])]=9999
    spec=dict(id='anomaly',kind='anomaly',alpha=200)
    a=r.fit(m,'precip_sum_mm',h,spec,cutoff);b=r.fit(changed,'precip_sum_mm',h,spec,cutoff)
    idx=pd.DatetimeIndex([date])
    assert np.allclose(r.predict(a,m,idx),r.predict(b,changed,idx))
    assert a['cutoff']==str(cutoff.date())


def test_selection_cannot_promote_weak_evidence():
    d=json.loads((r.OUT/'selection-frozen.json').read_text(encoding='utf-8'))
    assert d['final_opened'] is False
    for task in d['tasks'].values():
        if task['gate_pass']:
            assert task['gain']>=.03 and task['winning_years']>=3 and task['paired_CI95'][0]>0
            assert max(task['season_degradation'].values())<=.10
        else:assert task['spec']==task['baseline']


def test_quarterly_refit_label_availability():
    for p in r.OUT.glob('*-h*/*-dev.csv'):
        d=pd.read_csv(p)
        assert (pd.to_datetime(d.training_end)<=pd.to_datetime(d.feature_cutoff)).all()
        assert (pd.to_datetime(d.feature_cutoff)<pd.to_datetime(d.origin)).all()


def test_manifest_pins_all_existing_corpus_cards():
    manifest=json.loads((r.OUT/'data-manifest.json').read_text(encoding='utf-8'))
    cards=json.loads((r.OUT/'corpus-frozen.json').read_text(encoding='utf-8'))
    assert manifest['corpus_cards']==len(cards)==17
    assert len({c['id'] for c in cards})==17
    assert all(len(c['source']['sha256'])==64 for c in cards)


def test_finite_sample_radius_uses_ceiling_rank():
    assert r.empirical_radius(np.arange(10))==8
    assert r.empirical_radius([1,2,3])==3
