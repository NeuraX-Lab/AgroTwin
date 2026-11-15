"""Offline frozen-data research. Commands: freeze, develop, calibrate, final, verify.

Never downloads data or writes to v1/v2 artifacts. Final evaluation is a reused
retrospective diagnostic; its command requires an immutable selection ledger.
"""
import os
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
from pathlib import Path
import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
import numpy as np
import pandas as pd
import sklearn
from joblib import dump, load
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import v2_train as old
from v2_data import make_features
from v2_rag import RAG
P = json.loads((ROOT/'config/v3-protocol.json').read_text(encoding='utf-8'))
OUT = ROOT/'runs/research-v3'
REPORT = ROOT/'reports/v3/evidence'
FITS = 0


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def data():
    m = pd.read_csv(ROOT/'data/processed/v2/monthly.csv', index_col='period_start', parse_dates=True)
    if m.index.has_duplicates or not m.index.equals(pd.date_range(m.index.min(), m.index.max(), freq='MS')):
        raise ValueError('Monthly calendar is not complete and unique')
    return m


def freeze():
    if (OUT/'data-manifest.json').exists():
        verify_manifest()
        print('Existing immutable dataset verified')
        return
    roots = ['data/raw/v2', 'data/raw/local', 'data/processed/v2', 'data/processed/data-block-v1',
             'data/raw/resource-eda/power-dashboard-20261114', 'data/raw/satellite-context-2026-11-14',
             'runs/local-evidence-2026-11-14']
    files = set()
    for root in roots:
        files.update(p for p in (ROOT/root).rglob('*') if p.is_file())
    files.update(ROOT/p for p in ['config/rag-cards.json','config/v2-rag.json','config/v2-protocol.json',
                                 'config/v3-protocol.json','config/data-block-v1.json'])
    entries = [dict(path=p.relative_to(ROOT).as_posix(), bytes=p.stat().st_size, sha256=sha(p)) for p in sorted(files)]
    cards = RAG().cards
    m = data()
    sources = json.loads((ROOT/'data/processed/v2/manifest.json').read_text(encoding='utf-8'))['sources']
    manifest = dict(files=entries, nasa_sources=sources, aoi=json.loads((ROOT/'config/v2-protocol.json').read_text(encoding='utf-8'))['aoi'],
                    period=[str(m.index.min().date()),str(m.index.max().date())], rows=len(m),
                    schema={c:str(t) for c,t in m.dtypes.items()}, units=P['targets'],
                    local_scope='Frozen v2 references and contexts; no temporally aligned field weather/yield labels. Never pool stations/soil quantiles as target labels.',
                    corpus_cards=len(cards), raw_preserved=True, new_data=False)
    save(OUT/'data-manifest.json',manifest)
    save(REPORT/'data-manifest.json',manifest)
    save(OUT/'corpus-frozen.json',cards)
    save(REPORT/'corpus-frozen.json',cards)
    env=dict(python=platform.python_version(),sklearn=sklearn.__version__,numpy=np.__version__,pandas=pd.__version__,
             git_source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
             branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),
             protocol_sha256=sha(ROOT/'config/v3-protocol.json'))
    save(REPORT/'environment.json',env)
    print('Frozen',len(entries),'files;',len(cards),'cards;',len(m),'months')


def verify_manifest():
    manifest=json.loads((OUT/'data-manifest.json').read_text(encoding='utf-8'))
    for e in manifest['files']:
        if sha(ROOT/e['path']) != e['sha256']:
            raise ValueError('Frozen input changed: '+e['path'])
    return True


def metrics(y,p):
    e=np.asarray(p)-np.asarray(y)
    return dict(MAE=float(np.abs(e).mean()), RMSE=float(np.sqrt(np.mean(e**2))),bias=float(e.mean()),n=len(e))


def clip(p,target):
    if target=='precip_sum_mm': return np.maximum(p,0)
    if target=='air_rh_mean_pct': return np.clip(p,0,100)
    return np.asarray(p)


def fit(m,target,h,spec,cutoff):
    global FITS
    FITS+=1
    if FITS > P['budget']['max_candidate_fits']:
        raise RuntimeError('Fit budget exceeded')
    if spec['kind']=='legacy':
        s=spec['spec']
        if s['kind']=='blend':
            return dict(kind='blend',weight=s['weight'],base=fit(m,target,h,dict(kind='legacy',spec=s['base']),cutoff),
                        candidate=fit(m,target,h,dict(kind='legacy',spec=s['candidate']),cutoff))
        if s['kind']=='bias':
            return dict(kind='bias',bias=s['bias'],candidate=fit(m,target,h,dict(kind='legacy',spec=s['candidate']),cutoff),target=target)
        return dict(kind='legacy',artifact=old.fit(m,target,h,s,cutoff))
    y=m.loc[:cutoff,target].dropna()
    if spec.get('window'):
        y=y.loc[y.index>cutoff-pd.DateOffset(years=spec['window'])]
    aggregate='median' if spec['kind']=='median' else 'mean'
    climate=y.groupby(y.index.month).agg(aggregate)
    a=dict(kind=spec['kind'],target=target,h=h,spec=spec,climate=climate,cutoff=str(cutoff.date()),rows=len(y))
    if spec['kind']=='anomaly':
        f,cols=make_features(m,h,'expanded')
        # Each lag/rolling feature loses the TRAIN-ONLY seasonal mean for its own
        # target month. Pipeline parameters never see validation/test values.
        train_idx=y.index[f.loc[y.index,cols].notna().all(axis=1)]
        x=f.loc[train_idx,cols]
        a['feature_climate']=x.groupby(x.index.month).mean()
        x=x-a['feature_climate'].loc[x.index.month].set_axis(x.index)
        yy=y.loc[train_idx]-climate.loc[train_idx.month].to_numpy()
        a['cols']=cols
        a['model']=make_pipeline(StandardScaler(),Ridge(alpha=spec['alpha']))
        with threadpool_limits(limits=1):a['model'].fit(x,yy)
    return a


def predict(a,m,index):
    kind=a['kind']
    if kind=='legacy':return old.predict(a['artifact'],m,index)
    if kind=='blend':return a['weight']*predict(a['candidate'],m,index)+(1-a['weight'])*predict(a['base'],m,index)
    if kind=='bias':return clip(predict(a['candidate'],m,index)+a['bias'],a['target'])
    p=a['climate'].loc[index.month].to_numpy()
    if kind=='naive':p=m[a['target']].shift(12).loc[index].to_numpy()
    elif kind=='anomaly':
        f,_=make_features(m,a['h'],'expanded');x=f.loc[index,a['cols']]
        x=x-a['feature_climate'].loc[index.month].set_axis(index)
        with threadpool_limits(limits=1):p=p+a['model'].predict(x)
    return clip(p,a['target'])


def roll(m,target,h,spec,years):
    rows=[]
    index=m.index[m.index.year.isin(years)]
    for _, dates in pd.Series(index,index=index).groupby(index.to_period('Q')):
        idx=pd.DatetimeIndex(dates.to_numpy());cutoff=idx.min()-pd.DateOffset(months=h+1)
        a=fit(m,target,h,spec,cutoff)
        p=predict(a,m,idx)
        for date,v in zip(idx,p):
            rows.append(dict(date=str(date.date()),year=int(date.year),season='dry' if date.month in [12,1,2,3,4] else 'wet',
                             actual=float(m.loc[date,target]),prediction=float(v),training_end=str(cutoff.date()),
                             origin=str((date-pd.DateOffset(months=h)).date()),feature_cutoff=str((date-pd.DateOffset(months=h+1)).date())))
    return pd.DataFrame(rows)


def paired_ci(difference,years):
    groups=[np.asarray(difference)[np.asarray(years)==y] for y in sorted(set(years))]
    rng=np.random.default_rng(42)
    samples=[float(np.concatenate([groups[i] for i in rng.integers(0,len(groups),len(groups))]).mean()) for _ in range(2000)]
    return [float(x) for x in np.quantile(samples,[.025,.975])]


def develop():
    if (OUT/'selection-frozen.json').exists():raise FileExistsError('Use a fresh --out; do not overwrite selection')
    verify_manifest();m=data();start=time.perf_counter();selected={};summary=[]
    for target in P['targets']:
      for h in P['horizons_months']:
        key=f'{target}-h{h}'
        legacy=json.loads((ROOT/f'runs/v2/{key}/selection-frozen.json').read_text(encoding='utf-8'))['selected']
        specs=[dict(id='clim-median',kind='median'),dict(id='clim-mean',kind='mean'),dict(id='seasonal-naive',kind='naive'),
               dict(id='recent-10',kind='median' if target=='precip_sum_mm' else 'mean',window=10),
               dict(id='recent-20',kind='median' if target=='precip_sum_mm' else 'mean',window=20)]
        specs += [dict(id='season-anomaly-'+str(a),kind='anomaly',alpha=a) for a in [20,200,2000]]
        specs += [dict(id='v2-frozen',kind='legacy',spec=legacy)]
        # v1 HGB A8 equivalent with the SAME v2 latency and same full train history.
        # This is an adapted method, not a reproduction of historical v1's data.
        specs += [dict(id='v1-adapted',kind='legacy',spec=dict(id='v1-adapted',kind='hgb',group='v1',leaves=3,rate=.05,leaf=15))]
        records=[];predictions={}
        for spec in specs:
            d=roll(m,target,h,spec,P['development_years']);predictions[spec['id']]=d
            folder=OUT/key;folder.mkdir(parents=True,exist_ok=True);d.to_csv(folder/(spec['id']+'-dev.csv'),index=False)
            record=dict(spec=spec,**metrics(d.actual,d.prediction),folds=[dict(year=int(y),**metrics(q.actual,q.prediction)) for y,q in d.groupby('year')])
            records.append(record)
        baseline=min(records[:3],key=lambda r:r['MAE']);best=min(records[3:],key=lambda r:r['MAE'])
        b=predictions[baseline['spec']['id']];c=predictions[best['spec']['id']]
        diff=np.abs(b.actual-b.prediction)-np.abs(c.actual-c.prediction)
        ci=paired_ci(diff,b.year)
        wins=sum(float(diff[b.year==y].mean())>0 for y in sorted(set(b.year)))
        seasons={s:float(np.abs(c.actual[c.season==s]-c.prediction[c.season==s]).mean()/np.abs(b.actual[b.season==s]-b.prediction[b.season==s]).mean()-1) for s in ['dry','wet']}
        gain=1-best['MAE']/baseline['MAE']
        gate=gain>=.03 and wins>=3 and max(seasons.values())<=.10 and ci[0]>0
        chosen=best if gate else baseline
        selected[key]=dict(target=target,h=h,spec=chosen['spec'],baseline=baseline['spec'],
                           best_candidate=best['spec'],gate_pass=bool(gate),gain=float(gain),winning_years=wins,paired_CI95=ci,season_degradation=seasons)
        summary.append(dict(task=key,selected=chosen['spec']['id'],baseline=baseline['spec']['id'],selected_MAE=chosen['MAE'],
                            baseline_MAE=baseline['MAE'],candidate=best['spec']['id'],candidate_MAE=best['MAE'],gain=float(gain),gate_pass=bool(gate),paired_CI95=ci))
        save(folder/'development.json',dict(records=records,decision=selected[key]))
        save(REPORT/(key+'-development.json'),dict(records=records,decision=selected[key]))
        print(key,chosen['spec']['id'],'MAE',round(chosen['MAE'],4),'candidate gain',round(gain*100,2),'gate',gate,flush=True)
    ledger=dict(tasks=selected,protocol_sha256=sha(ROOT/'config/v3-protocol.json'),data_manifest_sha256=sha(OUT/'data-manifest.json'),
                final_opened=False,fits=FITS,seconds=time.perf_counter()-start,selection_utc=pd.Timestamp.now(tz='UTC').isoformat())
    save(OUT/'selection-frozen.json',ledger);save(REPORT/'selection-frozen.json',ledger);save(REPORT/'development-summary.json',summary)


def empirical_radius(errors,nominal=.8):
    e=np.sort(np.asarray(errors));rank=min(len(e),int(np.ceil((len(e)+1)*nominal)))
    return float(e[rank-1])


def calibrate():
    if (OUT/'bands-frozen.json').exists():raise FileExistsError('Use a fresh --out; do not overwrite calibration')
    verify_manifest()
    ledger=json.loads((OUT/'selection-frozen.json').read_text(encoding='utf-8'));m=data();bands={}
    for key,t in ledger['tasks'].items():
        d=roll(m,t['target'],t['h'],t['spec'],P['calibration_years'])
        d.to_csv(OUT/key/'calibration.csv',index=False)
        errors=np.abs(d.actual-d.prediction)
        bands[key]=dict(radius=empirical_radius(errors),n=len(errors),years=P['calibration_years'],nominal=.8)
        cutoff=m.index.max();a=fit(m,t['target'],t['h'],t['spec'],cutoff)
        a['meta']=dict(target=t['target'],h=t['h'],unit=P['targets'][t['target']],radius=bands[key]['radius'],dataset_sha256=sha(ROOT/'data/processed/v2/monthly.csv'))
        dump(a,OUT/key/'model.joblib')
    save(OUT/'bands-frozen.json',bands);save(REPORT/'bands-frozen.json',bands)
    print('Independent-of-selection calibration:',len(bands),'tasks')


def final():
    if (OUT/'final-opened.json').exists():raise FileExistsError('Final already opened. Run verify; no adaptive re-evaluation.')
    verify_manifest();ledger=json.loads((OUT/'selection-frozen.json').read_text(encoding='utf-8'))
    bands=json.loads((OUT/'bands-frozen.json').read_text(encoding='utf-8'));m=data()
    # Record the exact committed method before the FIRST read of final outcomes.
    save(OUT/'final-opened.json',dict(selection_sha256=sha(OUT/'selection-frozen.json'),bands_sha256=sha(OUT/'bands-frozen.json'),
                                    git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                                    opened_utc=pd.Timestamp.now(tz='UTC').isoformat(),independent_test=False))
    results=[]
    for key,t in ledger['tasks'].items():
        d=roll(m,t['target'],t['h'],t['spec'],P['final_diagnostic_years'])
        b=roll(m,t['target'],t['h'],t['baseline'],P['final_diagnostic_years'])
        legacy=json.loads((ROOT/f'runs/v2/{key}/selection-frozen.json').read_text(encoding='utf-8'))['selected']
        v2=roll(m,t['target'],t['h'],dict(kind='legacy',spec=legacy),P['final_diagnostic_years'])
        v1=roll(m,t['target'],t['h'],dict(kind='legacy',spec=dict(id='v1-adapted',kind='hgb',group='v1',leaves=3,rate=.05,leaf=15)),P['final_diagnostic_years'])
        d['baseline']=b.prediction;d['v2_frozen']=v2.prediction;d['v1_adapted']=v1.prediction
        radius=bands[key]['radius'];d['lower']=clip(d.prediction-radius,t['target']);d['upper']=clip(d.prediction+radius,t['target'])
        d.to_csv(OUT/key/'final-diagnostic.csv',index=False)
        diff=np.abs(d.actual-d.baseline)-np.abs(d.actual-d.prediction)
        result=dict(task=key,selected=t['spec']['id'],selected_metrics=metrics(d.actual,d.prediction),baseline_metrics=metrics(d.actual,d.baseline),
                    v2_frozen_metrics=metrics(d.actual,d.v2_frozen),v1_adapted_metrics=metrics(d.actual,d.v1_adapted),
                    gain=float(1-np.abs(d.actual-d.prediction).mean()/np.abs(d.actual-d.baseline).mean()),paired_CI95=paired_ci(diff,d.year),
                    coverage=float(((d.actual>=d.lower)&(d.actual<=d.upper)).mean()),mean_width=float((d.upper-d.lower).mean()),
                    groups=[dict(season=s,**metrics(q.actual,q.prediction),baseline_MAE=metrics(q.actual,q.baseline)['MAE']) for s,q in d.groupby('season')],
                    years=[dict(year=int(y),**metrics(q.actual,q.prediction),baseline_MAE=metrics(q.actual,q.baseline)['MAE']) for y,q in d.groupby('year')])
        results.append(result)
    save(REPORT/'final-diagnostic.json',dict(results=results,independent_test=False,selection_changed=False,warning=P['test_independence']))
    print('Final diagnostic stored; no selection changes permitted')


def verify():
    verify_manifest();m=data();checks=[]
    ledger=json.loads((OUT/'selection-frozen.json').read_text(encoding='utf-8'))
    for key,t in ledger['tasks'].items():
        d=pd.read_csv(OUT/key/(t['spec']['id']+'-dev.csv'))
        assert (pd.to_datetime(d.training_end)<=pd.to_datetime(d.feature_cutoff)).all()
        assert (pd.to_datetime(d.feature_cutoff)<pd.to_datetime(d.origin)).all()
        a=load(OUT/key/'model.joblib');date=m.index.max()+pd.DateOffset(months=t['h']+1)
        full=m.reindex(pd.date_range(m.index.min(),date,freq='MS'));idx=pd.DatetimeIndex([date])
        p=predict(a,full,idx);assert np.isfinite(p).all()
        checks.append(dict(task=key,forecast=float(p[0]),target_month=str(date.date()),artifact_bytes=(OUT/key/'model.joblib').stat().st_size))
    save(REPORT/'verification.json',dict(passed=True,models=checks,dataset_hashes_valid=True))
    print('Verified all models and frozen inputs')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['freeze','develop','calibrate','final','verify']);parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    if args.out:
        OUT=args.out.resolve()
        REPORT=OUT/'reports'
    globals()[args.command]()
