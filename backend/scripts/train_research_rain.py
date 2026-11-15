"""Bounded HGB A8/B10 tuning with chronological validation and frozen final test.

CPU only. Target is real POWER gridded rain; simulated farmer goals never become
weather covariates or labels. No generic CLI holdout promotion is reused.
"""
import os
os.environ['OMP_NUM_THREADS']='1'
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['MKL_NUM_THREADS']='1'
from pathlib import Path
import json,itertools,sys,platform,hashlib,shutil
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error,mean_squared_error
from threadpoolctl import threadpool_limits
from joblib import dump
import sklearn

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_data_block import feature_matrix
from fetch_satellite_context import save,sha,now
OUT=ROOT/'runs/ai-baseline-v1'
CFG=json.loads((ROOT/'config/data-block-v1.json').read_text(encoding='utf-8'))
A=CFG['core_features'];B=A+CFG['optional_features']

def metrics(y,p,base=None):
    result={'MAE_mm':float(mean_absolute_error(y,p)),'RMSE_mm':float(np.sqrt(mean_squared_error(y,p))),
            'bias_mm':float(np.mean(np.asarray(p)-np.asarray(y))),'n':len(y)}
    if base is not None:
        b=mean_absolute_error(y,base)
        result['MAE_skill_vs_naive']=float(1-result['MAE_mm']/b) if b else None
    return result

def fit_model(frame,features,params):
    m=HistGradientBoostingRegressor(max_iter=100,l2_regularization=1,early_stopping=False,random_state=42,**params)
    with threadpool_limits(limits=1):m.fit(frame[features],frame.target_precip_sum_mm)
    return m

def predict(m,frame,features):
    with threadpool_limits(limits=1):return np.maximum(0,m.predict(frame[features]))

def train():
    OUT.mkdir(parents=True,exist_ok=True)
    source=ROOT/'data/processed/data-block-v1/features/extension-b.csv'
    d=pd.read_csv(source,parse_dates=['target_period_start'])
    d['year']=d.target_period_start.dt.year
    assert len(d)==120 and d.target_precip_sum_mm.notna().all()
    results=[]
    for group,features in [('A8',A),('B10',B)]:
        for leaves,minimum,rate in itertools.product([3,7],[10,15],[.05,.1]):
            params={'max_leaf_nodes':leaves,'min_samples_leaf':minimum,'learning_rate':rate}
            fold_scores=[]
            for year in [2020,2021,2022,2023]:
                tr=d[d.year<year];va=d[d.year==year]
                m=fit_model(tr,features,params);p=predict(m,va,features)
                fold_scores.append({'year':year,'train_n':len(tr),**metrics(va.target_precip_sum_mm,p,va.P_lag12)})
            results.append(dict(group=group,params=params,folds=fold_scores,cv_MAE_mm=float(np.mean([v['MAE_mm'] for v in fold_scores]))))
    # Tune within development only. 2024 checks fixed per-group winners.
    winners={g:min([r for r in results if r['group']==g],key=lambda r:r['cv_MAE_mm']) for g in ['A8','B10']}
    dev=d[d.year<=2023];val=d[d.year==2024];test=d[d.year==2025]
    vp={};tp={};val_metrics={};test_metrics={};models={}
    for group,features in [('A8',A),('B10',B)]:
        m=fit_model(dev,features,winners[group]['params'])
        vp[group]=predict(m,val,features)
        val_metrics[group]=metrics(val.target_precip_sum_mm,vp[group],val.P_lag12)
    val_metrics['seasonal_naive']=metrics(val.target_precip_sum_mm,val.P_lag12)
    chosen=min(['A8','B10'],key=lambda g:val_metrics[g]['MAE_mm'])
    selected=chosen if val_metrics[chosen]['MAE_mm']<.95*val_metrics['seasonal_naive']['MAE_mm'] else 'seasonal_naive'
    frozen={'selected_from_2024':selected,'candidate_group':chosen,'winners':winners,'test_used_for_selection':False,
            'policy':'candidate needs >5% validation MAE improvement; final test only reports performance',
            'frozen_at_utc':now(),'source_sha256':sha(source)}
    save(OUT/'selection-frozen.json',frozen)
    # Both A/B final diagnostics are reported, never used to change frozen selection.
    for group,features in [('A8',A),('B10',B)]:
        m=fit_model(d[d.year<=2024],features,winners[group]['params']);models[group]=m
        tp[group]=predict(m,test,features);test_metrics[group]=metrics(test.target_precip_sum_mm,tp[group],test.P_lag12)
        dump(m,OUT/f'hgb-{group}-evaluation.joblib')
    test_metrics['seasonal_naive']=metrics(test.target_precip_sum_mm,test.P_lag12)
    pred=test[['target_period_start','target_precip_sum_mm','P_lag12']].copy()
    pred['HGB_A8']=tp['A8'];pred['HGB_B10']=tp['B10']
    pred['selected_prediction']=test.P_lag12.to_numpy() if selected=='seasonal_naive' else tp[selected]
    pred.to_csv(OUT/'test-predictions.csv',index=False)
    folds=[]
    for g,w in winners.items():
        for r in w['folds']:folds.append(dict(group=g,**r))
    pd.DataFrame(folds).to_csv(OUT/'rolling-validation.csv',index=False)
    save(OUT/'tuning.json',results)
    seasons=[]
    for label,months in [('dry',[12,1,2,3,4]),('wet',[5,6,7,8,9,10,11])]:
        mask=test.target_period_start.dt.month.isin(months)
        for g,p in [('A8',tp['A8']),('B10',tp['B10']),('seasonal_naive',test.P_lag12.to_numpy())]:
            seasons.append(dict(season=label,method=g,**metrics(test.loc[mask,'target_precip_sum_mm'],np.asarray(p)[mask])))
    report=dict(task='next_month_POWER_grid_rain',unit='mm/month',data_mode='gridded_estimates',generated_at_utc=now(),
        target='precip_sum_mm',horizon_months=1,input_sha256=sha(source),features={'A8':A,'B10':B},
        train_rows=96,validation_rows=12,test_rows=12,cv_years=[2020,2021,2022,2023],
        validation=val_metrics,test=test_metrics,seasonal_test_diagnostics=seasons,selected=selected,
        selection_basis='2024_validation_only',candidate_final_MAE_skill=test_metrics[chosen]['MAE_skill_vs_naive'],
        final_test_revealed_at_utc=now(),selection_changed_after_test=False,
        status='RESEARCH_ONLY',source_vintage='retrospective; calendar lags known, original historical availability not archived',
        evaluation_independence='2025rain held out from this tuning; not project-wide blind data; prior V5 temperature experiment separate',
        sklearn_version=sklearn.__version__,python_version=platform.python_version(),runtime='CPU single thread',
        imputation='native HGB missing branches; no target fill',scaling='none',outliers='retained',
        independent_Q1=False,field_rain_accuracy_established=False,farmer_goals_used_as_weather_features=False)
    save(OUT/'ml-evaluation.json',report)
    # Separate inference refit, not overwriting evaluation models or final-test predictions.
    env=pd.read_csv(ROOT/'data/processed/data-block-v1/monthly/environment.csv',parse_dates=['period_start']).set_index('period_start')
    future=env.index.max()+pd.offsets.MonthBegin()
    f=feature_matrix(env.reindex(env.index.union(pd.DatetimeIndex([future]))))
    known=f[f.target_precip_sum_mm.notna()&f[A].notna().all(axis=1)]
    row=f.loc[[future]];method=selected;fallback=None
    if method=='B10' and row[B].isna().any(axis=1).iloc[0]:
        method='A8' if val_metrics['A8']['MAE_mm']<.95*val_metrics['seasonal_naive']['MAE_mm'] else 'seasonal_naive'
        fallback='Latest SMAP features unavailable; no forward-fill'
    if method=='seasonal_naive':value=float(row.P_lag12.iloc[0])
    else:
        cols=A if method=='A8' else B
        im=fit_model(known,cols,winners[method]['params']);value=float(predict(im,row,cols)[0]);dump(im,OUT/'inference-research.joblib')
    forecast=dict(status='research_only',period_start=future.strftime('%Y-%m-%d'),horizon_months=1,value_mm=value,
        method=method,selected_validation_method=selected,fallback=fallback,data_through=env.index.max().strftime('%Y-%m'),
        source='POWER regional grid',uncertainty=None,operational_latency_verified=False,
        warning='Not a daily forecast, field rainfall truth, water demand or crop eligibility')
    save(OUT/'research-forecast.json',forecast)
    figures(pred,pd.DataFrame(folds),report)
    print(json.dumps({'validation':val_metrics,'test':test_metrics,'selected':selected,'forecast':forecast},indent=2))
    return report

def figures(pred,folds,report):
    fig,axes=plt.subplots(2,1,figsize=(11,6),sharex=True)
    dates=pd.to_datetime(pred.target_period_start)
    for c,label in [('target_precip_sum_mm','POWER historical estimates'),('P_lag12','Seasonal naive'),('HGB_A8','HGB A8'),('HGB_B10','HGB B10')]:axes[0].plot(dates,pred[c],marker='o',ms=3,label=label)
    axes[0].legend(fontsize=8);axes[0].set_ylabel('mm/month');axes[0].set_title('2025 final-year research test; rolling one-step, no field accuracy claim')
    axes[1].bar(dates,pred.selected_prediction-pred.target_precip_sum_mm,width=18,color='#336d84');axes[1].axhline(0,color='grey');axes[1].set_ylabel('Selected error (mm)')
    fig.tight_layout();fig.savefig(OUT/'01-rain-predictions.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(10,4))
    for g in ['A8','B10']:
        q=folds[folds.group==g];axes[0].plot(q.year,q.MAE_mm,marker='o',label=g)
    axes[0].set_ylabel('MAE mm');axes[0].set_title('Development rolling folds');axes[0].legend()
    names=list(report['test']);axes[1].bar(names,[report['test'][n]['MAE_mm'] for n in names],color=['#397d8c','#80a8af','#d49e39']);axes[1].set_title('Final 2025 MAE');axes[1].set_ylabel('mm')
    fig.tight_layout();fig.savefig(OUT/'02-ml-evaluation.png',dpi=150);plt.close(fig)

if __name__=='__main__':train()
