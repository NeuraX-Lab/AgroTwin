"""Saved-model inference and deterministic, evidence-linked conditional planning."""
from pathlib import Path
import sys,json,time
import numpy as np,pandas as pd
from joblib import load
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from v2_data import DATA,OUT,make_features
from v2_train import predict
from v2_rag import RAG
from research_rag import context_snapshot
from fetch_satellite_context import save,now,sha

def forecast(artifact,m,index):
 s=artifact['spec']
 if s['kind']=='blend':return s['weight']*forecast(artifact['candidate'],m,index)+(1-s['weight'])*forecast(artifact['base'],m,index)
 if s['kind']=='bias':
  p=forecast(artifact['candidate'],m,index)+s['bias']
  return np.maximum(0,p) if artifact['candidate'].get('target')=='precip_sum_mm' else p
 return predict(artifact,m,index)

def regenerate_forecasts():
 m=pd.read_csv(DATA/'monthly.csv',index_col='period_start',parse_dates=True)
 checks=[]
 for folder in sorted(OUT.glob('*-h*')):
  if not (folder/'model.joblib').exists():continue
  a=load(folder/'model.joblib');meta=a['meta'];h=meta['h'];date=m.index.max()+pd.DateOffset(months=h+1)
  full=m.reindex(pd.date_range(m.index.min(),date,freq='MS'));idx=pd.DatetimeIndex([date]);f,c=make_features(full,h,'expanded')
  # Enforce calendar semantics even across unobserved future months.
  assert np.isclose(f.loc[date,'precip_sum_mm_lag'+str(h+1)],m.precip_sum_mm.iloc[-1])
  value=float(forecast(a,full,idx)[0]);record=json.loads((folder/'forecast.json').read_text());r=meta['radius'];target=meta['target']
  record.update(value=value,lower=max(0,value-r) if target in ['precip_sum_mm','air_rh_mean_pct'] else value-r,upper=min(100,value+r) if target=='air_rh_mean_pct' else value+r,
                training_inference_calendar_verified=True,feature_data_cutoff=str(m.index.max().date()))
  save(folder/'forecast.json',record);checks.append(dict(task=folder.name,future_target=str(date.date()),lag_matches_latest_month=True))
 save(OUT/'inference-calendar-check.json',dict(checks=checks,reason='Full monthly calendar inserted before shifts. A development inference calendar gap was corrected; no final-test or model selection values changed.'))

def rules(farm,forecasts=None):
 results=[];evidence={'rice':['rice-awd-2024','rotation-historic'],'baby_corn':['babycorn-water','babycorn-duration','rotation-historic'],'mungbean':['mungbean-water','mungbean-calendar','rotation-historic']}
 conflicts=farm.get('conflicts',[]);has_conflict=bool(conflicts)
 for strategy,crop,label in [('R0','rice','Lúa → lúa → lúa'),('R1','baby_corn','Lúa → bắp non → lúa'),('R2','mungbean','Lúa → đậu xanh → lúa')]:
  reasons=[];missing=[];blocked=False
  if farm.get('current_crop') not in ['rice']:missing.append('Xác nhận cây/vụ trước là lúa để áp dụng chuỗi tham khảo')
  if not farm.get('window_start') or not farm.get('window_end'):missing.append('Khoảng ngày có thể trồng và lịch giống')
  if farm.get('irrigation') in [None,'unknown']:missing.append('Nguồn tưới')
  if farm.get('drainage') in [None,'unknown']:missing.append('Khả năng thoát nước')
  if crop!='rice' and farm.get('drainage')=='poor':blocked=True;reasons.append('Loại khỏi phương án hiện tại: người dùng báo thoát nước kém, chưa có biện pháp khắc phục cho cây cạn')
  if farm.get('irrigation')=='none':missing.append('Đối chiếu nguồn nước có thể sử dụng cho cả vụ; mưa tháng chưa đủ tính cân bằng nước')
  if crop=='mungbean' and (farm.get('saline') is True or farm.get('acid_sulfate') is True):blocked=True;reasons.append('Quy trình đậu xanh cảnh báo đất mặn/phèn; cần đánh giá và giải pháp địa phương trước khi xem lại')
  if crop=='mungbean' and (farm.get('saline') is None or farm.get('acid_sulfate') is None):missing.append('Kiểm đất/nước mặn và phèn; không suy từ ảnh NDVI')
  if farm.get('soil_ph') is None:missing.append('Số đo pH cùng phương pháp, độ sâu và ngày đo')
  elif not farm.get('ph_method') or not farm.get('soil_measured_at'):missing.append('pH thiếu phương pháp hoặc ngày đo, chưa dùng để kết luận')
  if has_conflict:missing.append('Đầu vào có nguồn mâu thuẫn, cần giải quyết trước');reasons.append('Tạm ngừng đề xuất áp dụng do dữ liệu mâu thuẫn')
  if farm.get('window_start') and farm.get('window_end') and (pd.Timestamp(farm['window_end'])-pd.Timestamp(farm['window_start'])).days<60 and crop!='rice':
   missing.append('Cửa sổ ngắn: phải xác nhận giống và ngày thu cuối, không dùng ngày thu lần đầu làm ngày giải phóng đất')
  if not blocked:reasons.append('Chuỗi có trong tài liệu tham khảo; chưa xác nhận hiệu quả hoặc suitability tại ruộng')
  results.append(dict(id=strategy,crop=crop,label=label,status='blocked' if blocked else 'needs_information' if missing else 'conditional_reference',rank=None,score=None,probability_of_success=None,reasons=reasons,missing_inputs=missing,evidence_ids=evidence[crop],calendar='Cần đối chiếu cửa sổ mùa vụ và thời gian thu cuối; không tự phát hành lịch gieo cụ thể',tradeoff='Cây cạn đòi hỏi tưới–tiêu khác lúa; chưa có ước lượng lợi nhuận/năng suất được kiểm chứng',domain_approved=False))
 # Order only by explicit farmer crop interest, never by invented yield/water benefit.
 interests=farm.get('crop_interests',[])
 results.sort(key=lambda x:(x['status']=='blocked',x['crop'] not in interests,x['id']))
 rain=next((x for x in (forecasts or []) if x['target']=='precip_sum_mm' and x['horizon_months']==1),None)
 outlook=None if rain is None else dict(target_month=rain['target_month'],rain_mm=rain['value'],range_mm=[rain['lower'],rain['upper']],interpretation='Dải ước tính mưa vùng cho một tháng, chưa biết ngày mưa và khả năng tiêu nước; dùng để chuẩn bị kiểm tra tưới–tiêu, không tự xác nhận cây phù hợp')
 return dict(options=results,input_origin='self_reported' if farm else 'unknown',farm=farm,conflicts=conflicts,climate_context=outlook,ranking_basis='explicit crop interests then reference order; no agronomic benefit ranking',goal=farm.get('goal','explore'),goal_next_action={'water':'Kiểm nguồn tưới, tiêu và nhu cầu nước theo giai đoạn','soil':'Đo đất đúng phương pháp và xác minh điều kiện chuyển sang cây cạn','yield':'Cần số liệu đối chứng giống/vụ/quản lý; chưa có model tăng năng suất','explore':'Bổ sung cây hiện tại, lịch vụ và nước trước khi áp dụng'}.get(farm.get('goal','explore')))

class Engine:
 def __init__(self):
  self.monthly=pd.read_csv(DATA/'monthly.csv',index_col='period_start',parse_dates=True)
  selected=json.loads((OUT/'rag-selection-frozen.json').read_text())['selected'];self.rag=RAG(selected['alpha'],selected['rerank'])
  self.evaluation=json.loads((OUT/'evaluation.json').read_text());self.forecasts=[json.loads(p.read_text()) for p in sorted(OUT.glob('*-h*/forecast.json'))]
  self.run_id='v2-'+sha(OUT/'evaluation.json')[:12]
 def overview(self):
  m=self.monthly.tail(24)
  return dict(schema_version='fieldshift-2',run_id=self.run_id,region_id='MT-BLOCK-01',label='Mỹ Thành, Đồng Tháp',coordinate=[106.021621,10.479098],coordinate_scope='research-pack anchor; place-name supplied by user',data_through=str(self.monthly.index[-1].date()),forecasts=self.forecasts,
   months=[dict(date=str(d.date()),rain=float(r.precip_sum_mm),temp=float(r.air_temp_mean_c),rh=float(r.air_rh_mean_pct),coverage=1,qa='pass') for d,r in m.iterrows()],
   context=context_snapshot(),evaluation=self.evaluation,qa=json.loads((OUT/'data-qa.json').read_text()),rag_metrics=json.loads((OUT/'rag-final.json').read_text())['metrics'],rules=rules({},self.forecasts),
   source_mode='real NASA gridded estimates and local references; no simulated weather or crop labels')
 def analyze(self,farm,question=None):
  t=time.perf_counter();result=dict(schema_version='fieldshift-2',run_id=self.run_id,status='research_only',generated_at_utc=now(),region_id='MT-BLOCK-01',decision=rules(farm,self.forecasts),forecasts=self.forecasts,
    rag=self.rag.answer(question) if question else None,input_origin='self_reported_unverified',domain_approved=False)
  result['latency_ms']=(time.perf_counter()-t)*1000
  return result

if __name__=='__main__':regenerate_forecasts()
