"""Deterministic DATA release: QA, units, causal feature tables and relational context.

No fitting, imputation, model training, recommendation, embeddings or network calls.
"""
from pathlib import Path
import calendar
import json
import shutil
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from fetch_satellite_context import save, sha, now

CFG=json.loads((ROOT/'config/data-block-v1.json').read_text(encoding='utf-8'))
OUT=ROOT/CFG['processed_bundle']
LOCAL=ROOT/CFG['local_bundle']
POWER=ROOT/'data/raw/resource-eda/power-dashboard-20261114/daily.json'
SMAP=ROOT/'data/raw/satellite-context-2026-11-14/smap-l4/centroid-daily.csv'

def csv(df,name):
    p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
    df.to_csv(p,index=False,encoding='utf-8-sig')

def aggregate_months(daily, operations, min_coverage=1.0):
    """Full calendar denominator even if input begins/ends mid-month; no infill."""
    if daily.index.has_duplicates or not daily.index.is_monotonic_increasing:
        raise ValueError('Daily keys must be unique and sorted')
    expected=pd.date_range(daily.index.min().to_period('M').start_time,
                           daily.index.max().to_period('M').end_time.normalize(),freq='D')
    d=daily.reindex(expected)
    out=pd.DataFrame(index=pd.date_range(expected.min(),expected.max(),freq='MS'))
    for col,operation in operations.items():
        count=d[col].resample('MS').count()
        coverage=count/out.index.days_in_month
        raw=d[col].resample('MS').sum(min_count=1) if operation=='sum' else d[col].resample('MS').mean()
        out[col]=raw.where(coverage>=min_coverage)
        out[col+'_coverage']=coverage
        out[col+'_observed_days']=count
        out[col+'_available_days_statistic']=raw
    return out

def monthly_power():
    j=json.loads(POWER.read_text(encoding='utf-8-sig'))
    assert j['header']['time_standard']=='UTC'
    parameters=j['properties']['parameter']
    expected={'PRECTOTCORR':'mm/day','T2M':'C','RH2M':'%'}
    for c,u in expected.items(): assert j['parameters'][c]['units']==u
    d=pd.DataFrame(parameters)
    d.index=pd.to_datetime(d.index,format='%Y%m%d');d=d.sort_index().astype(float)
    d=d.mask(d.eq(j['header']['fill_value']))
    invalid_rain=d.PRECTOTCORR.lt(0)
    invalid_rh=~d.RH2M.between(0,100)&d.RH2M.notna()
    temp_order=(d.T2M_MIN>d.T2M)|(d.T2M>d.T2M_MAX)
    d.loc[invalid_rain,'PRECTOTCORR']=np.nan;d.loc[invalid_rh,'RH2M']=np.nan
    m=aggregate_months(d,{'PRECTOTCORR':'sum','T2M':'mean','T2M_MIN':'mean','T2M_MAX':'mean','RH2M':'mean'})
    ren={'PRECTOTCORR':'precip_sum_mm','T2M':'air_temp_mean_c','RH2M':'air_rh_mean_pct',
         'T2M_MIN':'mean_daily_min_temp_c','T2M_MAX':'mean_daily_max_temp_c'}
    m=m.rename(columns={c:ren.get(c,c) for c in m.columns})
    m['source_id']='NASA_POWER_DAILY_2015_202610';m['spatial_support']='POWER_grid_not_farm'
    m['day_convention']='UTC';m['record_kind']='gridded_environmental_estimate'
    return m,dict(daily_records=len(d),invalid_rain=int(invalid_rain.sum()),invalid_rh=int(invalid_rh.sum()),
                  temp_order_flags=int(temp_order.sum()),monthly_rows=len(m),monthly_precip_missing=int(m.precip_sum_mm.isna().sum()))

def monthly_smap():
    d=pd.read_csv(SMAP,index_col='date',parse_dates=True).sort_index()
    invalid={}
    for c in ['SFMC','RZMC']:
        bad=~d[c].between(0,1)&d[c].notna();invalid[c]=int(bad.sum());d.loc[bad,c]=np.nan
    m=aggregate_months(d[['SFMC','RZMC']],{'SFMC':'mean','RZMC':'mean'},CFG['monthly_smap_min_calendar_coverage'])
    return m,dict(invalid=invalid,months=len(m),source_kind='SMAP_L4_assimilated_model_via_POWER',
                  native_support='approximately9km',version_warning='upstream_L4_version_not_fully_pinned; source status=reviewing')

def feature_matrix(monthly):
    if monthly.index.has_duplicates: raise ValueError('Duplicate months')
    expected=pd.date_range(monthly.index.min(),monthly.index.max(),freq='MS')
    if not monthly.index.equals(expected): raise ValueError('Calendar monthly keys must be contiguous before shift')
    f=pd.DataFrame(index=monthly.index)
    for lag in [1,2,3,12]: f[f'P_lag{lag}']=monthly.precip_sum_mm.shift(lag)
    f['T2M_lag1']=monthly.air_temp_mean_c.shift(1)
    f['RH2M_lag1']=monthly.air_rh_mean_pct.shift(1)
    f['month_sin']=np.sin(2*np.pi*f.index.month/12)
    f['month_cos']=np.cos(2*np.pi*f.index.month/12)
    for c in ['SFMC','RZMC']: f[c+'_lag1']=monthly[c].shift(1)
    f['target_precip_sum_mm']=monthly.precip_sum_mm
    f['target_period_start']=f.index.strftime('%Y-%m-%d')
    f['history_cutoff_exclusive']=f.index.strftime('%Y-%m-%d')
    f['forecast_origin_month']=(f.index-pd.offsets.MonthBegin()).strftime('%Y-%m-%d')
    f['region_id']=CFG['region_id']
    f['n_missing_core_features']=f[CFG['core_features']].isna().sum(axis=1)
    f['n_missing_optional_features']=f[CFG['optional_features']].isna().sum(axis=1)
    f['historical_available_at_verified']=False
    f['availability_policy']='previous_completed_calendar_month; retrospective_hindcast_only'
    return f

def contexts():
    s=pd.read_csv(ROOT/'runs/satellite-context-2026-11-14/sentinel2/scene-qa-and-block-summary.csv')
    s['context_qualified']=s.block_valid_fraction>=CFG['sentinel_context_min_block_valid_fraction']
    s['qualified_block_ndvi_mean']=s.block_ndvi_mean.where(s.context_qualified)
    s['qualified_block_evi_mean']=s.block_evi_mean.where(s.context_qualified)
    s['region_id']=CFG['region_id'];s['source_id']='COPERNICUS_S2_C1_L2A'
    s['scope']='199pixel_centres_in_digitised_block; not_crop_labels'
    s['model_feature_selected']=False;s['acquisition_year_is_current']=False
    s['available_at_verified']=False
    csv(s,'context/sentinel2-scenes.csv')
    m=pd.read_csv(ROOT/'runs/satellite-context-2026-11-14/modis/regional-composite-summary.csv')
    m['context_qualified']=m.valid_fraction>=CFG['modis_context_min_regional_valid_fraction']
    m['qualified_regional_mean']=m.regional_mean.where(m.context_qualified)
    m['region_id']=CFG['region_id'];m['source_id']='NASA_MOD13Q1'
    m['scope']='17x17native_cells;16day_composite;changing_valid_pixel_support'
    m['model_feature_selected']=False;m['available_at_verified']=False
    csv(m,'context/modis-composites.csv')
    for p in sorted((LOCAL/'tables').glob('*.csv')):
        dest=OUT/'local'/p.name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
    farmcols=['record_id','region_id','observed_at','available_at','property','value','unit','method',
              'depth_top_cm','depth_bottom_cm','source_id','quality_flag']
    csv(pd.DataFrame(columns=farmcols),'farm-input/observations.csv')
    csv(pd.DataFrame(columns=['region_id','effective_from','available_at','current_crop','cultivar','sown_at',
                'irrigation_source','drainage_description','source_id','verification_status']), 'farm-input/management.csv')
    save(OUT/'farm-input/schema-status.json',dict(status='provisional_waiting_for_user_detail',actual_farm_records=0,
         no_assumptions_about_user_fields=True,merge_policy='region_and_valid_time_and_available_at; property_unit_method_depth_required'))
    return dict(sentinel_scenes=len(s),sentinel_qualified_scenes=int(s.context_qualified.sum()),
                modis_rows=len(m),modis_qualified_rows=int(m.context_qualified.sum()),actual_farm_records=0)

def dictionary():
    rows=[]
    for c in CFG['core_features']+CFG['optional_features']:
        moisture=c.startswith(('SFMC','RZMC'))
        unit='m3/m3' if moisture else 'mm/month' if c.startswith('P_') else 'degC' if c.startswith('T2M') else '%' if c.startswith('RH2M') else 'unitless'
        rows.append(dict(feature=c,status='selected_optional_ablation' if moisture else 'selected_core_v1',unit=unit,
            source='SMAP_L4_via_POWER' if moisture else 'known_calendar' if c.startswith('month_') else 'POWER',
            grain='region_target_month',role='future_ML_input_not_trained',
            transform='lag_of_full_calendar_month_mean' if moisture or c.startswith(('T2M','RH2M')) else 'known_target_month_cyclic_encoding' if c.startswith('month_') else 'lag_of_full_calendar_month_rain_sum',
            imputation='none',learned_scaling='none',historical_availability='hindcast_assumption_not_archived_vintage'))
    for c,src,grain in [('NDVI/EVI','MODIS','regional_composite'),('block_NDVI/EVI','Sentinel2','block_scene'),
                        ('pH/texture/SOC/N/CEC','SoilGrids_or_measured_source','site_depth_method_statistic'),
                        ('station_rain_temperature','local_station_reference','station_period'),
                        ('drainage_irrigation_calendar','farm_or_local_rule','site_effective_period')]:
        rows.append(dict(feature=c,status='context_only_separate_table',unit='see_source_dictionary',source=src,grain=grain,
            role='context_map_or_reference',transform='source_specific_QA_and_units;not_broadcast_into_training_rows',imputation='none',learned_scaling='none',historical_availability='retain_source_date_and_unknowns'))
    csv(pd.DataFrame(rows),'dictionary.csv')

def build():
    OUT.mkdir(parents=True,exist_ok=True)
    p,pqa=monthly_power();s,sqa=monthly_smap()
    both=p.join(s,how='left',validate='one_to_one')
    both['region_id']=CFG['region_id']
    both['period_start']=both.index.strftime('%Y-%m-%d')
    both['period_end_exclusive']=(both.index+pd.offsets.MonthBegin()).strftime('%Y-%m-%d')
    both['SMAP_source_id']='NASA_POWER_SMAP_L4'
    both['SMAP_spatial_support']='approximately9km_model_grid_not_farm'
    both['SMAP_qa_status']=np.where(both[['SFMC','RZMC']].notna().all(axis=1),'calendar_complete','missing_or_incomplete_calendar')
    both['qa_status']=np.where(both.precip_sum_mm.notna(),'core_calendar_complete','core_incomplete')
    csv(both.reset_index(drop=True),'monthly/environment.csv')
    # One future target row preserves unknown target; optional source does not shorten backbone.
    future=both.index.max()+pd.offsets.MonthBegin()
    history=both.reindex(both.index.union(pd.DatetimeIndex([future])))
    f=feature_matrix(history)
    f['split_role']=['reserved_test' if y==2025 else 'reserved_validation' if y==2024 else 'development' if 2016<=y<=2023 else 'outside_evaluation' for y in f.index.year]
    candidates=f[(f.index>=CFG['training_period'][0])&(f.index<=CFG['training_period'][1])]
    keys=['region_id','target_period_start','forecast_origin_month','history_cutoff_exclusive','split_role',
          'historical_available_at_verified','availability_policy']
    csv(candidates[keys+CFG['core_features']+['target_precip_sum_mm','n_missing_core_features']], 'features/core-a.csv')
    csv(candidates[keys+CFG['core_features']+CFG['optional_features']+['target_precip_sum_mm','n_missing_core_features','n_missing_optional_features']], 'features/extension-b.csv')
    csv(f[f.index==future], 'features/latest-origin-candidate.csv')
    ctx=contexts();dictionary()
    # Secondary local reference remains diagnostic; never replaces model target or calibration.
    ref=pd.read_csv(LOCAL/'tables/mytho-monthly-rain-reference.csv',parse_dates=['period_start'])
    compare=ref.merge(p[['precip_sum_mm']].rename(columns={'precip_sum_mm':'POWER_AOI_precip_mm'}),left_on='period_start',right_index=True,how='left',validate='many_to_one')
    compare['difference_station_minus_AOI_mm']=compare.precip_sum_mm-compare.POWER_AOI_precip_mm
    compare['interpretation']='station_vs_grid_spatial_diagnostic;not_forecast_metrics_or_field_accuracy'
    csv(compare,'qa/local-rain-vs-power-context.csv')
    checks=dict(unique_month_keys=not both.index.has_duplicates,backbone_months_preserved=len(both)==len(p),
        no_imputed_rain=True,no_farm_values_fabricated=ctx['actual_farm_records']==0,
        core_feature_rows=len(candidates),core_rows_complete=int(candidates[CFG['core_features']+['target_precip_sum_mm']].notna().all(axis=1).sum()),
        optional_complete_rows=int(candidates[CFG['optional_features']].notna().all(axis=1).sum()),
        split_counts=candidates.split_role.value_counts().to_dict(),
        models_fitted=False,learned_transforms_fitted=False,RAG_index_built=False,independent_Q1_K1_approved=False)
    if not checks['unique_month_keys'] or not checks['backbone_months_preserved']: raise ValueError('Fusion cardinality failure')
    save(OUT/'qa/validation.json',dict(technical_checks=checks,POWER=pqa,SMAP=sqa,context=ctx,
        release_status='partial_pending_farm_and_independent_review',features_selected=CFG['core_features'],
        optional_features=CFG['optional_features'],preprocessing_config_sha256=sha(ROOT/'config/data-block-v1.json')))
    inputs=[POWER,SMAP,LOCAL/'manifest.json',ROOT/'config/data-block-v1.json',
            ROOT/'runs/satellite-context-2026-11-14/sentinel2/scene-qa-and-block-summary.csv',
            ROOT/'runs/satellite-context-2026-11-14/modis/regional-composite-summary.csv']
    (OUT/'README.md').write_text('''# DATA block v1

Điểm vào: `monthly/environment.csv` (NASA backbone), `features/core-a.csv` (8biến), `features/extension-b.csv` (+2SMAP), `context/`, `local/`, `farm-input/`, `dictionary.csv`, `qa/validation.json`.

Đơn vị/QA được xử lý bằng quy tắc xác định; chưa fit scaler/imputer/model. Monthly rain chỉ xuất khi đủ ngày calendar UTC; SMAP monthly mean cũng cần đủ ngày calendar. Available-days statistic chỉ phục vụ QA, không dùng thay feature đạt chuẩn. Dữ liệu trước tháng đích được shift theo lịch đầy đủ; không shuffle, không lấy tương lai để điền.

Tập core giữ 120 target months2016–2025 với split chỉ dự trữ, chưa training/evaluation. Bổ sung SMAP giữ nguyên số hàng và null khi thiếu. `latest-origin-candidate.csv` có target chưa biết, retrospective availability caveat; chưa phải forecast.

LOCAL station không được nối vào target hoặc tự bias-correct; diagnostic station-vs-grid không phải MAE forecast. Đất có method/depth/statistic; ảnh có scene/composite và coverage. FARM INPUT chưa có bản ghi. Independent Q1/K1 còn chờ review; vùng/ruộng hỗ trợ khác nhau được giữ nguyên.
''',encoding='utf-8')
    generated=[dict(path=str(q.relative_to(OUT)),sha256=sha(q),bytes=q.stat().st_size) for q in sorted(OUT.rglob('*')) if q.is_file() and q.name!='manifest.json']
    save(OUT/'manifest.json',dict(schema_version=CFG['schema_version'],generated_at_utc=now(),region_id=CFG['region_id'],
        area=json.loads((ROOT/'config/resource-eda.json').read_text(encoding='utf-8'))['aoi'],
        status='partial',data_kind='gridded_estimates_and_separate_local_references',
        input_refs=[dict(path=str(q.relative_to(ROOT)),sha256=sha(q)) for q in inputs],outputs=generated,
        source_files_gitignored=True,training_run=False,scientific_approval=False))
    print(json.dumps(checks,indent=2))

if __name__=='__main__':build()
