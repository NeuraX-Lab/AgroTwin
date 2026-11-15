"""Evidence-gated feasibility assessment and reproducible ML recommendation.

This module makes *recommendations*, not empirical claims about agronomic outcomes.
"""
from __future__ import annotations
import json, re, shutil, subprocess
from pathlib import Path
from .core import timestamp

NASA_TOKENS={'nasa','power','gpm','smap','modis','viirs','ecostress','landsat','grace','gedi'}
TIME_TOKENS=('date','time','month','period','year','timestamp','day')
RAIN_TOKENS=('rain','precip','prcp')
TEMP_TOKENS=('temp','t2m','heat')
LOCATION_TOKENS=('region','lat','lon','longitude','latitude','geo','crs','field_id')
SOIL_TOKENS=('soil','crop','rotation','cultivar','season','constraint')


def _contains(values,tokens):
    return [v for v in values if any(t in v.lower() for t in tokens)]


def _table_columns(file):
    result=file.get('inspection',{})
    tables=[]
    if 'columns' in result:tables.append((file['path'],result.get('columns',[]),result.get('sample_rows',0)))
    for s in result.get('sheets',[]):tables.append((file['path']+'#'+s['sheet'],s.get('columns',[]),s.get('sample_rows',0)))
    for s in result.get('tables',[]):tables.append((file['path']+'#'+s['table'],s.get('columns',[]),s.get('sample_rows',0)))
    return tables


def machine_info():
    # Hints provided by the user are not equivalent to measured free RAM/VRAM.
    out={'user_reported_hardware':{'gpu':'NVIDIA RTX 4060 Laptop','gpu_total_vram_gb':8,'system_ram_gb':32,
                                   'uncertain':'Reported Lenovo model and RAM must be checked on actual machine'},
         'measured_gpu':None,'measured_ram_gb':None}
    try:
        import psutil
        out['measured_ram_gb']=round(psutil.virtual_memory().total/1024**3,1)
        out['measured_available_ram_gb']=round(psutil.virtual_memory().available/1024**3,1)
    except ImportError:pass
    if shutil.which('nvidia-smi'):
        try:
            t=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total,memory.free','--format=csv,noheader,nounits'],
                             capture_output=True,text=True,timeout=4,check=True)
            out['measured_gpu']=[x.strip() for x in t.stdout.strip().splitlines() if x.strip()]
        except (subprocess.TimeoutExpired,subprocess.CalledProcessError):pass
    return out


def analyze_fit(scan:dict,root:Path):
    files=scan['files']
    tables=[item for f in files for item in _table_columns(f)]
    allcols=sorted({c for _,columns,_ in tables for c in columns})
    paths=[f['path'].lower() for f in files]
    time_cols=_contains(allcols,TIME_TOKENS)
    rain_cols=_contains(allcols,RAIN_TOKENS)
    temp_cols=_contains(allcols,TEMP_TOKENS)
    location_cols=_contains(allcols,LOCATION_TOKENS)
    soil_cols=_contains(allcols,SOIL_TOKENS)
    spatial=[f['path'] for f in files if f['kind'] in ('raster','vector','geojson','array')]
    issues=[]; strengths=[]
    source_file=root/'_source.json'
    source=None
    if source_file.is_file():
        try:
            source=json.loads(source_file.read_text(encoding='utf-8'))
        except (ValueError,UnicodeError):issues.append('Invalid _source.json: source metadata could not be parsed.')
    else:issues.append('No _source.json: source provenance, license and observation mode are unverified.')
    declared_nasa=bool(source and str(source.get('provider','')).lower().startswith('nasa'))
    if not declared_nasa:issues.append('No NASA provenance declared in _source.json. NASA data cannot be assumed from filenames.')
    elif source.get('verification_status')!='verified':issues.append('NASA provider claimed but source marked unverified; manually validate product/version and URL.')
    else:strengths.append('NASA provider and verification status declared (requires independent review).')
    if tables:strengths.append(f'{len(tables)} table or spreadsheet tables discoverable.')
    else:issues.append('No accessible tabular table; satellite formats may require specialist reader/aggregation.')
    if time_cols:strengths.append(f'Time candidate columns: {", ".join(time_cols[:6])}')
    else:issues.append('No candidate time column. Temporal features and forecast are blocked.')
    if rain_cols or temp_cols: strengths.append('Climate candidate fields found (units and meaning still require review).')
    else:issues.append('No identifiable rainfall/temperature feature columns.')
    if location_cols or spatial:strengths.append('Spatial candidate fields or files are present.')
    else:issues.append('No region/coordinate or spatial metadata detected.')
    if soil_cols:strengths.append('Agronomic candidate columns exist; scientific constraints remain unverified.')
    else:issues.append('No crop/soil/rotation constraints found; ranking remains needs_review.')
    if any(x.get('status')=='error' for x in files):issues.append('Some files failed inspection; do not use as if complete.')
    if any(x.get('status')=='missing_dependency' for x in files):issues.append('Some formats need optional readers; their content has not been examined.')
    observed=(source or {}).get('data_mode')=='observed'
    if not observed:issues.append('Dataset not explicitly marked observed; synthetic/mixed/unknown cannot be claimed as scientific evidence.')
    readiness='needs_review'
    if declared_nasa and rain_cols and time_cols and (soil_cols or Path(root/'domain-constraints.csv').exists()):
        readiness='candidate_requires_domain_qa'
    blockers=[x for x in issues if any(w in x.lower() for w in ('provenance','agronomic','constraints','unverified','no nasa'))]
    questions=[
        'What AOI, time range, resolution, product version and UTC/LST convention apply?',
        'Which crop/soil-season constraints does Bich verify with local sources?',
        'Can Quang Luat independently validate units, aggregation, missingness and temporal split?',
        'Does a measured target exist for training or just an explainable decision-support ranking?',
        'Can the output be demonstrated independently of live hardware and internet?'
    ]
    return {'generated_at':timestamp(),'challenge':'Field Shift: Adapting Farms with NASA Data',
            'working_concept':'NeuraX AgroTwin','status':readiness,'columns_detected':allcols,
            'candidate_time_columns':time_cols,'candidate_rain_columns':rain_cols,'candidate_temp_columns':temp_cols,
            'candidate_location_columns':location_cols,'candidate_domain_columns':soil_cols,'spatial_files':spatial,
            'table_refs':[x[0] for x in tables],'strengths':strengths,'gaps':issues,'hard_gate_notes':blockers,
            'owner_assessment':{
                'DATA_GEO':'Viet (Technical Lead); verify sources and map each raw field',
                'AI_SCOPING':'Hung and Viet; specify target, baseline and metric',
                'DOMAIN':'Bich; scientific validity of crop/soil/season rules',
                'QA_EVAL':'Quang Luat; independent QC and holdout audit',
                'UI_API':'Hieu; consume versioned A1 output',
                'HARDWARE':'Tieu An; sensor context, never ground truth satellite'},
            'questions':questions,
            'recommendation':'Proceed with evidence-gated exploratory analysis; keep agronomic recommendations and forecast unavailable until their individual gates pass.'}


def build_model_plan(fit:dict,scan:dict,machine:dict)->dict:
    climate=bool(fit['candidate_rain_columns'] or fit['candidate_temp_columns'])
    all_tabular=[f for f in scan['files'] if f['kind'] in ('table','spreadsheet','sqlite')]
    bytes_sum=sum(f['size_bytes'] for f in all_tabular)
    # Risk check conservative: dataframe processing can use several times source bytes.
    ram_gb=machine['user_reported_hardware']['system_ram_gb']  # conservative laptop profile, even when run in cloud
    estimated_ram_gb=round((bytes_sum/1024**3)*6+0.5,2)
    memory_risk=estimated_ram_gb>0.55*ram_gb
    return {
        'generated_at':timestamp(),'decision_status':'advisory_not_validated',
        'intended_products':[
            {'task':'crop_rotation_decision_support','method':'hard constraints + explainable weighted ranking',
             'train_required':False,'required_inputs':['verified K1 crop/soil/season rules','QA-approved climate features','farmer priorities'],
             'output':['eligibility','criterion_scores','warnings','evidence_ids'],
             'state':'blocked_by_domain_review' if not fit['candidate_domain_columns'] else 'candidate_requires_review'},
            {'task':'next_month_rainfall_forecast','method':'seasonal-naive baseline then HistGradientBoostingRegressor with lag features',
             'train_required':True,'target':'precip_sum_mm','horizon_months':1,
             'minimum_history_months':60,'test_months':12,'split':'time_ordered_no_shuffle',
             'candidate_params':{'max_iter':100,'learning_rate':0.06,'max_leaf_nodes':15,'min_samples_leaf':3,'l2_regularization':1.0,'random_state':42},
             'metric':'MAE_mm','promote_when':'candidate beats seasonal-naive on holdout, >5% improvement suggested not guaranteed',
             'state':'candidate_check_full_dataset' if climate and fit['candidate_time_columns'] else 'unavailable_missing_target_or_time'}],
        'other_model_options':[
            {'when':'Large, valid tabular training dataset with target labels and solid baseline',
             'consider':'LightGBM/CatBoost/XGBoost (CPU first) with time-aware validation'},
            {'when':'Satellite imagery + labeled segmentation targets, enough examples and scientific evaluation',
             'consider':'Efficient pretrained CNN/U-Net patch training; GPU 8GB may require batch=1-4, mixed precision; cloud if memory exceeds capacity'},
            {'when':'Unlabeled EO/raster only',
             'consider':'EDA, vegetation indices, seasonality and rule-based outputs before supervised deep learning'}],
        'hardware_route':{'primary':'local_cpu','optional_gpu':'RTX 4060 Laptop 8GB only if verified installed & task benefits',
                          'cloud_fallback':'notebooks/cloud_training.ipynb',
                          'estimated_tabular_memory_gb':estimated_ram_gb,'memory_risk':memory_risk,
                          'reported_ram_gb':ram_gb,'measured_execution_environment_ram_gb':machine.get('measured_ram_gb'),'rule':'If memory estimate >55% RAM or OOM, downsample/chunk or move training to cloud; do not auto-upload data.'},
        'api_contract':'/v1/status, /v1/reports/fit, /v1/reports/model-plan, /v1/forecast/next',
        'warning':'No accuracy, crop yield, water savings, or hardware feasibility has been measured from the actual challenge data.'}


def research_tasks(fit):
    q=[
        {'question':'Determine NASA POWER official product, parameter, temporal and spatial metadata for selected AOI',
         'search':'site:power.larc.nasa.gov/docs/services/api/ temporal daily AG precipitation T2M PRECTOTCORR',
         'primary_url':'https://power.larc.nasa.gov/docs/services/api/temporal/daily/'},
        {'question':'Find authoritative local crop, soil, season constraints matching AOI',
         'search':'Vietnam crop rotation soil climate seasonal agriculture FAO research local province',
         'primary_url':'https://www.fao.org/'},
        {'question':'Check HistGradientBoostingRegressor parameters and time series leakage risks',
         'search':'site:scikit-learn.org HistGradientBoostingRegressor TimeSeriesSplit',
         'primary_url':'https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html'},
        {'question':'Check Colab GPU restrictions and availability at actual training time',
         'search':'site:research.google.com/colaboratory/faq.html GPU limits',
         'primary_url':'https://research.google.com/colaboratory/faq.html'}]
    if fit['spatial_files']:
        q.append({'question':'Identify CRS, resolution and resampling policy for raster/vector sources',
            'search':'site:usgs.gov geospatial raster reprojection satellite data scale aggregation',
            'primary_url':'https://www.usgs.gov/'})
    return {'generated_at':timestamp(),'rule':'Every literature claim needs URL, retrieval date, scope, limitation, and reviewer. Search queries are not citations.',
            'tasks':q}
