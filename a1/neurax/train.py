"""Time-aware Field Shift rainfall forecasting with strict baseline comparison.

No trained model is assumed useful unless it beats the holdout seasonal naive.
"""
from __future__ import annotations
import json, math
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd
from .core import write_json, timestamp, sha256_file


def _months_after(s, n=1):
    return (pd.Timestamp(s)+pd.DateOffset(months=n)).strftime('%Y-%m-%d')

def _features(y,dates):
    # Values from PREVIOUS periods only; one-step-ahead with observed history.
    rows=[]
    for i in range(12,len(y)):
        m=dates[i].month
        rows.append([float(y[i-1]),float(y[i-12]),float(np.mean(y[i-3:i])),
                     math.sin(2*math.pi*m/12),math.cos(2*math.pi*m/12)])
    return np.asarray(rows,dtype=float)

def train_forecast(input_csv:Path,out:Path,target='precip_sum_mm',date_col='period_start',region=None):
    input_csv=Path(input_csv).resolve();out=Path(out).resolve()
    if input_csv.suffix.lower()!='.csv':raise ValueError('Only CSV forecast training is currently implemented.')
    if not input_csv.is_file():raise FileNotFoundError(input_csv)
    df=pd.read_csv(input_csv,low_memory=False)
    required={target,date_col}
    if not required.issubset(df):raise ValueError(f'Missing columns: {sorted(required-set(df.columns))}')
    if 'region_id' in df:
        unique=list(df['region_id'].dropna().unique())
        if region is not None:df=df.loc[df.region_id.astype(str)==region].copy()
        elif len(unique)>1:raise ValueError('Multiple regions found. Pass --region explicitly; do not pool different climate zones.')
    if df.empty:raise ValueError('No rows after filtering.')
    df[date_col]=pd.to_datetime(df[date_col],errors='raise',utc=True)
    if df[date_col].duplicated().any():raise ValueError('Duplicate period keys; choose correct aggregation grain first.')
    df=df.sort_values(date_col).reset_index(drop=True)
    if df[target].isna().any():raise ValueError('Missing target values. Explicitly qualify, omit or impute with a documented policy first.')
    values=pd.to_numeric(df[target],errors='raise').astype(float).to_numpy()
    if not np.isfinite(values).all():raise ValueError('Non-finite numeric values in target.')
    if target=='precip_sum_mm' and (values<0).any():raise ValueError('Precipitation values cannot be negative.')
    dates=list(df[date_col].dt.tz_localize(None))
    if not all(d.day==1 for d in dates):raise ValueError('Expected monthly period_start with day=1.')
    for i in range(1,len(dates)):
        if dates[i] != dates[i-1]+pd.DateOffset(months=1):
            raise ValueError(f'Missing/irregular month between {dates[i-1]} and {dates[i]}; resolve coverage explicitly.')
    if len(df)<60:raise ValueError(f'Need >=60 contiguous monthly periods for this initial protocol; got {len(df)}')
    x=_features(values,dates)
    y=values[12:]
    holdout=12
    if len(x)-holdout<36:raise ValueError('Not enough training rows after lags and holdout.')
    x_train,x_test=x[:-holdout],x[-holdout:]
    y_train,y_test=y[:-holdout],y[-holdout:]
    baseline=x_test[:,1]  # same month previous year; no leakage.
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.metrics import mean_absolute_error, mean_squared_error
    from joblib import dump
    model=HistGradientBoostingRegressor(max_iter=100,learning_rate=0.06,max_leaf_nodes=15,
           min_samples_leaf=3,l2_regularization=1.0,random_state=42,early_stopping=False)
    model.fit(x_train,y_train)
    preds=np.maximum(0,model.predict(x_test)) if target=='precip_sum_mm' else model.predict(x_test)
    bmae=float(mean_absolute_error(y_test,baseline))
    cmae=float(mean_absolute_error(y_test,preds))
    brmse=float(np.sqrt(mean_squared_error(y_test,baseline)))
    crmse=float(np.sqrt(mean_squared_error(y_test,preds)))
    promote=(cmae < bmae*.95) if bmae>0 else False
    # Even promoted candidate is still exploratory: only one holdout window.
    out.mkdir(parents=True,exist_ok=True)
    if promote:
        model.fit(x,y)
        dump(model,out/'forecast.joblib',compress=3)
    unit='mm/month' if target=='precip_sum_mm' else 'source-unit (verify)'
    evaluation={'generated_at':timestamp(),'input_file':str(input_csv),'input_sha256':sha256_file(input_csv),
         'region':str(region or (df['region_id'].iloc[0] if 'region_id' in df else 'unspecified')),
         'n_months':len(df),'train_n':len(x_train),'holdout_n':len(x_test),
         'holdout_start':dates[-holdout].strftime('%Y-%m-%d'),
         'holdout_end':dates[-1].strftime('%Y-%m-%d'),'target':target,'target_unit':unit,
         'features':['lag_1','lag_12','mean_previous_3','month_sin','month_cos'],
         'protocol':'last 12 months holdout; rolling one-step features use observed previous months',
         'metrics':{'seasonal_naive_mae':bmae,'candidate_mae':cmae,
                    'seasonal_naive_rmse':brmse,'candidate_rmse':crmse},
         'promotion_gate':{'threshold_relative_mae_improvement':0.05,'candidate_promoted':promote},
         'model':'HistGradientBoostingRegressor' if promote else 'seasonal_naive',
         'limitations':['Single final-year holdout is not proof of generalization across regions or climate shifts.',
                        'No crop yield, soil-health or water-savings claims supported.',
                        'Requires evidence for target units, provenance, and representative AOI.',
                        'If data_mode is synthetic these are smoke metrics only, NOT scientific findings.']}
    write_json(out/'evaluation.json',evaluation)
    metadata={'generated_at':timestamp(),'target':target,'date_column':date_col,
              'region':evaluation['region'],'next_period':_months_after(dates[-1]),
              'last_12_values':[float(x) for x in values[-12:]],
              'trained_candidate_available':promote,
              'selection':'candidate' if promote else 'seasonal_naive',
              'unit':unit,'input_sha256':evaluation['input_sha256']}
    write_json(out/'forecast_metadata.json',metadata)
    pred=predict_next(out)
    write_json(out/'next_forecast.json',pred)
    return evaluation


def predict_next(model_dir:Path):
    from joblib import load
    model_dir=Path(model_dir).resolve()
    meta=json.loads((model_dir/'forecast_metadata.json').read_text(encoding='utf-8'))
    past=np.asarray(meta['last_12_values'],dtype=float)
    if past.size!=12:raise ValueError('Exactly 12 lagged periods required.')
    method=meta['selection']
    if method=='candidate':
        # Never unpickle untrusted weights: only load a locally created model from this run.
        model_path=model_dir/'forecast.joblib'
        if not model_path.is_file():raise FileNotFoundError(model_path)
        m=pd.Timestamp(meta['next_period']).month
        row=np.asarray([[past[-1],past[0],np.mean(past[-3:]),
                         math.sin(2*math.pi*m/12),math.cos(2*math.pi*m/12)]],dtype=float)
        model=load(model_path)
        value=float(model.predict(row)[0])
        if meta['target']=='precip_sum_mm':value=max(0.0,value)
    else:value=float(past[0])
    return {'schema_version':'0.1','generated_at':timestamp(),'result_kind':'forecast',
            'status':'partial','target':meta['target'],'period_start':meta['next_period'],
            'horizon_months':1,'value':round(value,4),'unit':meta['unit'],'method':method,
            'source_data_sha256':meta.get('input_sha256'),
            'warnings':['A model estimate, not certainty or an agronomic recommendation.','Verify source data mode and evaluation before public claims.']}
