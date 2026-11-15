"""Offline V4.1 EDA and predeclared temperature experiment, separate from crop A1.

Run: python -m neurax.agrotwin.research --out runs/agrotwin-v41-research
No user click trains a model. No experimental artifact is production-approved.
"""
import argparse
import json
import platform
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
import joblib
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

from ..core import write_json, sha256_file
from ..train import _features
from .data import load, qualify
from .inputs import Period, fingerprint

PROTOCOL = {
    'version':'v41-temperature-1', 'target':'T2M monthly mean', 'unit':'degC',
    'horizon_months':1, 'validation_years':[2021,2022,2023], 'final_years':[2024,2025],
    'features':['lag1','lag12','previous3mean','month_sin','month_cos'],
    'candidate_leaf_counts':[3,7], 'seed':42,
    'production_gate':'disabled: no reviewed K1 consumer and limited regional evaluation',
    'research_comparison_gate':'selected on validation only; report final without reselection',
}


def metrics(y,p):
    residual=np.asarray(p)-np.asarray(y)
    return {'n':len(y),'mae_degC':float(np.mean(abs(residual))),
            'rmse_degC':float(np.sqrt(np.mean(residual**2))), 'bias_degC':float(np.mean(residual))}


def candidate(leaves):
    return HistGradientBoostingRegressor(max_iter=100,learning_rate=.06,max_leaf_nodes=leaves,
        min_samples_leaf=6,l2_regularization=1,random_state=42,early_stopping=False)


def experiment(rows,out):
    dates=pd.to_datetime([r['date'] for r in rows]);y=np.array([r['temp'] for r in rows],dtype=float)
    if len(rows)<120 or not np.isfinite(y).all():raise ValueError('Need >=120 complete monthly temperature targets')
    if list(dates)!=list(pd.date_range(dates[0],periods=len(dates),freq='MS')):raise ValueError('Noncontiguous monthly series')
    x=_features(y,list(dates));targets=y[12:];ds=dates[12:]
    final=ds.year>=2024
    if list(ds[final].year.unique())!=[2024,2025] or sum(final)!=24:raise ValueError('Protocol requires full untouched 2024–25 holdout')
    folds=[];scores={}
    with threadpool_limits(limits=1):
        for leaves in PROTOCOL['candidate_leaf_counts']:
            actual=[];predicted=[]
            for year in PROTOCOL['validation_years']:
                train=ds.year<year;val=ds.year==year
                model=candidate(leaves).fit(x[train],targets[train]);p=model.predict(x[val])
                actual.extend(targets[val]);predicted.extend(p)
                folds.append({'candidate':leaves,'year':year,'train_n':int(sum(train)),
                              'max_training_target':str(ds[train][-1].date()),
                              'candidate_metrics':metrics(targets[val],p),'baseline_metrics':metrics(targets[val],x[val,1])})
            scores[str(leaves)]=metrics(actual,predicted)['mae_degC']
        validation=(ds.year>=2021)&(ds.year<=2023)
        baseline_score=metrics(targets[validation],x[validation,1])['mae_degC']
        best=min(scores,key=scores.get)
        selected='hgb_'+best if scores[best]<baseline_score*.95 else 'seasonal_naive'
        # Selection frozen BEFORE final labels are used in metrics.
        selection={'candidate':selected,'validation_mae':scores,'baseline_validation_mae':baseline_score,
                   'gate_relative_improvement':.05,'final_holdout_used_for_selection':False}
        write_json(out/'selection.json',selection)
        model=candidate(int(best)).fit(x[~final],targets[~final])
        p=model.predict(x[final]);base=x[final,1]
        final_report={'candidate':metrics(targets[final],p),'baseline':metrics(targets[final],base),
            'selected_method':selected,'selected_metrics':metrics(targets[final],p if selected.startswith('hgb') else base),
            'by_season':{},'high_temperature_months':{}}
        for name,months in [('DJF',[12,1,2]),('MAM',[3,4,5]),('JJA',[6,7,8]),('SON',[9,10,11])]:
            mask=np.isin(ds[final].month,months)
            final_report['by_season'][name]={'candidate':metrics(targets[final][mask],p[mask]),'baseline':metrics(targets[final][mask],base[mask])}
        threshold=float(np.quantile(targets[~final],.9));mask=targets[final]>=threshold
        final_report['high_temperature_months']={'threshold_train_only_degC':threshold,'n':int(sum(mask)),
            'candidate':metrics(targets[final][mask],p[mask]) if sum(mask) else None,
            'note':'Descriptive slice, not heat-wave detection or crop stress threshold'}
        from joblib import dump
        dump(model,out/'candidate.joblib',compress=3)
        artifact_sha=sha256_file(out/'candidate.joblib')
    predictions=pd.DataFrame({'date':ds[final].strftime('%Y-%m-%d'),'actual_degC':targets[final],
                              'candidate_degC':p,'baseline_degC':base})
    predictions.to_csv(out/'final_predictions.csv',index=False)
    return {'protocol':PROTOCOL,'folds':folds,'selection':selection,'final_e1':final_report,
            'environment':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,
                           'sklearn':sklearn.__version__,'joblib':joblib.__version__},
            'final_holdout_dates':['2024-01-01','2025-12-01'],'latest_fit_target':'2023-12-01',
            'train_final_n':int(sum(~final)),'final_holdout_n':int(sum(final)),
            'decision':'RESEARCH_ONLY','inference_consumer':'Power research evidence only; no production prediction or A1 join',
            'artifact_sha256':artifact_sha,'production_approved':False,
            'interpretation':'Internal temporal E1, not independent external scientific validation; no crop outcome labels.',
            'limitations':['One regional grid, 11 years; autocorrelated monthly records.',
                           'Rolling one-step uses previous observed test months, not a 24-month forecast.',
                           'Validation and final test are different dates; protocol was designed after historic source availability, not a prospective trial.',
                           'Final metrics cannot justify retrospective model reselection or crop suitability.']}


def run(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    raw=load('climate.json')
    rows=[r for year in range(2015,2026) for r in qualify(raw['months'],Period(start=f'{year}-01-01',end=f'{year+1}-01-01'),raw['source']['flags'])]
    data=pd.DataFrame(rows);data[['date','rain','temp','coverage','qa']].to_csv(out/'normalized.csv',index=False)
    monthly=data.assign(month=pd.to_datetime(data.date).dt.month).groupby('month')[['rain','temp']].agg(['mean','std','min','max'])
    monthly.to_csv(out/'seasonality.csv')
    summary={'schema_version':'agrotwin-research-1','source':raw['source'],'normalized_sha256':sha256_file(out/'normalized.csv'),
        'source_payload_sha256':fingerprint(raw),'implementation_sha256':sha256_file(Path(__file__)),
        'n_months':len(data),'period':['2015-01-01','2025-12-01'],'missing':data[['rain','temp']].isna().sum().to_dict(),
        'duplicates':int(data.date.duplicated().sum()),'zero_rain_months':int((data.rain==0).sum()),
        'qa_counts':data.qa.value_counts().to_dict(),'retained_flags':raw['source']['flags'],
        'descriptive_statistics':data[['rain','temp']].describe().to_dict(),
        'feasibility':{'climate_temperature':'RESEARCH_ONLY:132 monthly targets,120 lagged samples',
                       'crop_suitability':'NOT_TRAINABLE_WITH_AVAILABLE_LABELS',
                       'sensor_anomalies':'NOT_TRAINABLE_WITH_AVAILABLE_LABELS: no verified real log'},
        'raw_reconstruction':'Curated monthly payload reproducible. Original raw daily source bytes not asserted reacquired.',
        'experiment':experiment(rows,out)}
    write_json(out/'report.json',summary)
    # Standard plotting tools, no generated scientific illustration.
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(2,1,figsize=(10,6),layout='constrained')
    ax[0].plot(pd.to_datetime(data.date),data.temp);ax[0].set_ylabel('Regional T2M (degC)')
    ax[1].bar(pd.to_datetime(data.date),data.rain,width=24);ax[1].set_ylabel('Rain (mm/month)')
    fig.suptitle('NASA POWER regional cache 2015–2025; not field measurements')
    fig.savefig(out/'eda.png',dpi=140);plt.close(fig)
    return summary


def production_inference_gate(report):
    # Research approval never authorizes product inference, even with favorable errors.
    if report.get('decision')!='PROMOTED' or report.get('production_approved') is not True:
        raise ValueError('Unvalidated/research model cannot serve production inference')
    raise ValueError('No production consumer/approved artifact exists in this release')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',default='runs/agrotwin-v41-research');a=p.parse_args()
    r=run(a.out);print(json.dumps({'months':r['n_months'],'experiment':r['experiment']['decision'],'final':r['experiment']['final_e1']},indent=2))
