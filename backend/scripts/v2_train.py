"""Bounded pre-registered rolling hindcasts. Never select using final test."""
import os
os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['MKL_NUM_THREADS']='1'
from pathlib import Path
import sys,json,time,copy,platform
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor,ExtraTreesRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits
from joblib import dump,load
import sklearn
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from v2_data import DATA,OUT,PROTOCOL,make_features
from fetch_satellite_context import save,sha,now

FITS=0;START=time.perf_counter()
def metric(y,p):
    e=np.asarray(p)-np.asarray(y)
    return dict(MAE=float(np.abs(e).mean()),RMSE=float(np.sqrt(np.mean(e*e))),bias=float(e.mean()),n=len(e))

def candidates(target):
    specs=[dict(id=x,kind=x,group='v1',complexity=i) for i,x in enumerate(['clim_median','clim_mean','seasonal_naive','persistence'])]
    specs += [dict(id=f'ridge-{a}',kind='ridge',group='expanded',alpha=a,complexity=4) for a in [1,20,200]]
    for group in ['v1','expanded']:
        for leaves in [3,7]:
            for rate in [.03,.08]:
                for leaf in [12,30]:
                    specs.append(dict(id=f'hgb-{group}-{leaves}-{rate}-{leaf}',kind='hgb',group=group,leaves=leaves,rate=rate,leaf=leaf,complexity=6))
    for leaf in [5,15]:specs.append(dict(id=f'et-{leaf}',kind='et',group='expanded',leaf=leaf,complexity=8))
    if target=='precip_sum_mm':
        for leaves in [3,7]:specs.append(dict(id=f'hgb-log-{leaves}',kind='hgb',group='expanded',leaves=leaves,rate=.05,leaf=20,log=True,complexity=6))
    return specs

def fit(m,target,h,spec,cutoff,seed=42):
    global FITS
    if FITS>=PROTOCOL['budget']['max_candidate_fits'] or time.perf_counter()-START>1800:raise RuntimeError('Experiment budget exhausted')
    f,cols=make_features(m,h,spec['group']);mask=(f.index<=cutoff)&f[cols].notna().all(axis=1)&m[target].notna()
    x=f.loc[mask,cols];y=m.loc[mask,target];kind=spec['kind'];model=None
    climate=y.groupby(y.index.month).median() if kind=='clim_median' else y.groupby(y.index.month).mean()
    if kind in ['hgb','et','ridge']:
        if kind=='hgb':model=HistGradientBoostingRegressor(max_iter=120,max_leaf_nodes=spec['leaves'],learning_rate=spec['rate'],min_samples_leaf=spec['leaf'],l2_regularization=5,early_stopping=False,random_state=seed)
        elif kind=='et':model=ExtraTreesRegressor(n_estimators=80,min_samples_leaf=spec['leaf'],max_features=.8,n_jobs=1,random_state=seed)
        else:model=make_pipeline(SimpleImputer(strategy='median'),StandardScaler(),Ridge(alpha=spec['alpha']))
        # Ridge predicts deviations from train-only climatology; log-rain is an explicit ablation.
        yy=y-climate.loc[y.index.month].to_numpy() if kind=='ridge' else np.log1p(y) if spec.get('log') else y
        with threadpool_limits(limits=1):model.fit(x,yy)
        FITS+=1
    return dict(spec=spec,model=model,cols=cols,climate=climate,target=target,h=h,training_end=str(cutoff),training_rows=len(x))

def predict(artifact,m,index):
    s=artifact['spec'];target=artifact['target'];h=artifact['h'];f,_=make_features(m,h,s['group']);kind=s['kind']
    climate=artifact['climate'].loc[index.month].to_numpy()
    if kind in ['clim_mean','clim_median']:p=climate
    elif kind=='seasonal_naive':p=m[target].shift(12).loc[index].to_numpy()
    elif kind=='persistence':p=m[target].shift(h+1).loc[index].to_numpy()
    else:
        with threadpool_limits(limits=1):p=artifact['model'].predict(f.loc[index,artifact['cols']])
        if kind=='ridge':p=p+climate
        if s.get('log'):p=np.expm1(p)
    if target=='precip_sum_mm':p=np.maximum(p,0)
    if target=='air_rh_mean_pct':p=np.clip(p,0,100)
    return p

def rolling(m,target,h,spec,years):
    rows=[]
    for year in years:
        idx=m.index[m.index.year==year];cutoff=idx.min()-pd.DateOffset(months=h+1)
        model=fit(m,target,h,spec,cutoff);p=predict(model,m,idx)
        rows.extend(dict(date=str(d.date()),year=year,actual=float(m.loc[d,target]),prediction=float(v)) for d,v in zip(idx,p))
    return pd.DataFrame(rows)

def block_ci(errors,seed=42):
    a=np.asarray(errors);rng=np.random.default_rng(seed);n=len(a);out=[]
    for _ in range(1500):
        starts=rng.integers(0,n,size=int(np.ceil(n/12)));idx=np.concatenate([(s+np.arange(12))%n for s in starts])[:n];out.append(a[idx].mean())
    return list(np.quantile(out,[.025,.975]).astype(float))

def reproduce_v1():
    import train_research_rain as v1
    original=OUT.parent/'ai-baseline-v1'
    v1.OUT=OUT/'v1-reproduction';v1.train()
    old=json.loads((original/'ml-evaluation.json').read_text());new=json.loads((v1.OUT/'ml-evaluation.json').read_text())
    matches=all(np.isclose(old['test'][k]['MAE_mm'],new['test'][k]['MAE_mm'],atol=1e-8) for k in old['test'])
    save(OUT/'v1-reproduction.json',dict(source_commit='2e810c73661debd6c062b954ce94a4156c8f121e',source='scripts/train_research_rain.py in Lab only',reproduced=bool(matches),test_2025=new['test'],warning='Exposed v1 test; no independent v2 selection evidence'))
    if not matches:raise ValueError('v1 reproduction mismatch')

def train():
    # Plotting belongs to offline experiments, not the inference cold start.
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    m=pd.read_csv(DATA/'monthly.csv',index_col='period_start',parse_dates=True);OUT.mkdir(parents=True,exist_ok=True)
    if not json.loads((OUT/'data-qa.json').read_text())['critical_pass']:raise ValueError('DATA gate failed')
    reproduce_v1();allresults=[];runtime=[]
    for target in PROTOCOL['targets']:
      for h in PROTOCOL['horizons_months']:
        begin=time.perf_counter();name=f'{target}-h{h}';folder=OUT/name;folder.mkdir(exist_ok=True)
        records=[];preds={};specs=candidates(target)
        for spec in specs:
            p=rolling(m,target,h,spec,PROTOCOL['development_validation_years']);preds[spec['id']]=p
            records.append(dict(spec=spec,**metric(p.actual,p.prediction),folds=[dict(year=int(y),**metric(x.actual,x.prediction)) for y,x in p.groupby('year')]))
        # A development-driven second stage: bias correction and regularized blend, no test labels.
        best=min(records,key=lambda x:x['MAE']);base=min([x for x in records if x['spec']['kind'].startswith('clim') or x['spec']['kind']=='seasonal_naive'],key=lambda x:x['MAE'])
        bp=preds[best['spec']['id']];baseline=preds[base['spec']['id']]
        for weight in [.25,.5,.75]:
            s=dict(id='blend-'+str(weight),kind='blend',base=base['spec'],candidate=best['spec'],weight=weight,group='expanded',complexity=9)
            p=bp.copy();p.prediction=weight*bp.prediction+(1-weight)*baseline.prediction
            preds[s['id']]=p;records.append(dict(spec=s,**metric(p.actual,p.prediction),folds=[dict(year=int(y),**metric(x.actual,x.prediction)) for y,x in p.groupby('year')]))
        # Bias learned only from earlier development folds, not same-fold errors.
        corrected=bp.copy();corrected['correction']=0.
        for year in PROTOCOL['development_validation_years']:
            past=bp[bp.year<year]
            if len(past):corrected.loc[corrected.year==year,'correction']=float(np.median(past.actual-past.prediction))
        corrected.prediction+=corrected.correction
        if target=='precip_sum_mm':corrected.prediction=corrected.prediction.clip(lower=0)
        spec=dict(id='bias-corrected',kind='bias',candidate=best['spec'],bias=float(np.median(bp.actual-bp.prediction)),group='expanded',complexity=8)
        preds[spec['id']]=corrected;records.append(dict(spec=spec,**metric(corrected.actual,corrected.prediction),folds=[dict(year=int(y),**metric(x.actual,x.prediction)) for y,x in corrected.groupby('year')]))
        threshold=min(x['MAE'] for x in records)*1.02
        selected=min([x for x in records if x['MAE']<=threshold],key=lambda x:(x['spec']['complexity'],x['MAE']))
        chosen=selected['spec'];selected_dev=preds[chosen['id']]
        # Compare multiple seeds before freeze for stochastic chosen candidate, no test-based choice.
        seed_scores=[]
        stochastic=chosen if chosen['kind'] in ['hgb','et'] else chosen.get('candidate')
        if stochastic and stochastic['kind'] in ['hgb','et']:
            for seed in [17,91]:
                vals=[]
                for year in PROTOCOL['development_validation_years']:
                    idx=m.index[m.index.year==year];a=fit(m,target,h,stochastic,idx.min()-pd.DateOffset(months=h+1),seed);vals.extend(zip(m.loc[idx,target],predict(a,m,idx)))
                yy,pp=zip(*vals);seed_scores.append(dict(seed=seed,**metric(yy,pp)))
        save(folder/'selection-frozen.json',dict(selected=chosen,development=records,seed_stability=seed_scores,protocol_sha256=sha(ROOT/'config/v2-protocol.json'),data_sha256=sha(DATA/'monthly.csv'),test_used=False,frozen_at_utc=now()))
        def composite(spec,cutoff):
            if spec['kind']=='blend':return dict(spec=spec,base=composite(spec['base'],cutoff),candidate=composite(spec['candidate'],cutoff))
            if spec['kind']=='bias':return dict(spec=spec,candidate=composite(spec['candidate'],cutoff))
            return fit(m,target,h,spec,cutoff)
        def infer(a,index):
            if a['spec']['kind']=='blend':return a['spec']['weight']*infer(a['candidate'],index)+(1-a['spec']['weight'])*infer(a['base'],index)
            if a['spec']['kind']=='bias':return np.maximum(0,infer(a['candidate'],index)+a['spec']['bias']) if target=='precip_sum_mm' else infer(a['candidate'],index)+a['spec']['bias']
            return predict(a,m,index)
        idx=m.index[m.index.year.isin(PROTOCOL['new_locked_test_years'])];cutoff=idx.min()-pd.DateOffset(months=h+1)
        artifact=composite(chosen,cutoff);base_art=composite(base['spec'],cutoff)
        prediction=infer(artifact,idx);bpred=infer(base_art,idx)
        residual=np.abs(selected_dev.actual-selected_dev.prediction);radius=float(np.quantile(residual,.8,method='higher'))
        lower=prediction-radius;upper=prediction+radius
        if target=='precip_sum_mm':lower=np.maximum(0,lower)
        if target=='air_rh_mean_pct':lower=np.maximum(0,lower);upper=np.minimum(100,upper)
        test=pd.DataFrame(dict(date=idx,actual=m.loc[idx,target].to_numpy(),prediction=prediction,baseline=bpred,lower=lower,upper=upper));test.to_csv(folder/'final-test.csv',index=False)
        improvement=np.abs(test.actual-test.baseline)-np.abs(test.actual-test.prediction)
        report=dict(target=target,unit=PROTOCOL['targets'][target],horizon_months=h,selected=chosen,development_MAE=selected['MAE'],baseline=base['spec'],baseline_development_MAE=base['MAE'],test=metric(test.actual,test.prediction),baseline_test=metric(test.actual,test.baseline),
            MAE_improvement_pct=float(100*(1-np.abs(test.actual-test.prediction).mean()/np.abs(test.actual-test.baseline).mean())),paired_improvement_mm_or_target_unit_CI95_block12=block_ci(improvement),
            folds=selected['folds'],seed_stability=seed_scores,interval=dict(nominal=.8,radius=radius,coverage=float(((test.actual>=test.lower)&(test.actual<=test.upper)).mean()),mean_width=float((test.upper-test.lower).mean()),method='empirical rolling-development absolute errors; dependent-time coverage not guaranteed'),
            groups=[dict(season=label,**metric(q.actual,q.prediction),baseline_MAE=metric(q.actual,q.baseline)['MAE']) for label,q in [('dry',test[pd.to_datetime(test.date).dt.month.isin([12,1,2,3,4])]),('wet',test[~pd.to_datetime(test.date).dt.month.isin([12,1,2,3,4])])]],
            test_years=[2012,2013,2014],test_revealed_at_utc=now(),selection_changed_after_test=False,independent_field_validation=False)
        save(folder/'evaluation.json',report);allresults.append(report)
        # Forecast next full calendar target(s), using same schema and known-data cutoff.
        target_date=m.index.max()+pd.DateOffset(months=h+1);m=m.reindex(pd.date_range(m.index.min(),target_date,freq='MS'))
        operational=composite(chosen,m.index[m[target].notna()].max());operational['meta']=dict(target=target,h=h,radius=radius,unit=PROTOCOL['targets'][target],feature_pipeline_version=2)
        artifact_path=folder/'model.joblib';dump(operational,artifact_path);reloaded=load(artifact_path)
        p1=infer(operational,pd.DatetimeIndex([target_date]));p2=infer(reloaded,pd.DatetimeIndex([target_date]));assert np.allclose(p1,p2)
        value=float(p1[0]);lo=max(0,value-radius) if target in ['precip_sum_mm','air_rh_mean_pct'] else value-radius;hi=min(100,value+radius) if target=='air_rh_mean_pct' else value+radius
        save(folder/'forecast.json',dict(target=target,unit=PROTOCOL['targets'][target],horizon_months=h,target_month=str(target_date.date()),value=value,lower=lo,upper=hi,nominal_coverage=.8,backtest_coverage=report['interval']['coverage'],method=chosen['id'],issued_at_utc=now(),data_through=str(pd.read_csv(DATA/'monthly.csv').period_start.iloc[-1]),kind='monthly_research_hindcast_method',historical_vintage_verified=False,warning='Not daily weather, field measurement, seasonal dynamical forecast or exact irrigation demand'))
        runtime.append(dict(task=name,seconds=time.perf_counter()-begin,artifact_bytes=artifact_path.stat().st_size,save_load_consistent=True));m=pd.read_csv(DATA/'monthly.csv',index_col='period_start',parse_dates=True)
        selected_dev.to_csv(folder/'development-predictions.csv',index=False)
        fig,ax=plt.subplots(figsize=(10,3));ax.plot(idx,test.actual,label='POWER history');ax.plot(idx,test.prediction,label='Selected');ax.plot(idx,test.baseline,alpha=.6,label='Baseline');ax.fill_between(idx,lower,upper,alpha=.15);ax.set_title(name+' | frozen 2012-2014 test');ax.set_ylabel(PROTOCOL['targets'][target]);ax.legend(fontsize=8);fig.tight_layout();fig.savefig(folder/'test.png',dpi=130);plt.close(fig)
        print(name,'selected',chosen['id'],'test',report['test']['MAE'],'baseline',report['baseline_test']['MAE'],flush=True)
    save(OUT/'evaluation.json',dict(results=allresults,runtime=runtime,fits=FITS,seconds=time.perf_counter()-START,sklearn=sklearn.__version__,python=platform.python_version(),budget=PROTOCOL['budget'],stop_reason='Preregistered bounded families complete; no tuning using final test',created_at_utc=now()))

if __name__=='__main__':train()
