"""Metadata-aware bilingual evidence retrieval and constrained sourced rendering."""
from pathlib import Path
import sys,json,re,time
import numpy as np
from sklearn.feature_extraction.text import CountVectorizer,TfidfVectorizer
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from research_rag import EvidenceRAG,norm
from fetch_satellite_context import save,sha,now
OUT=ROOT/'runs/v2'
NEW=[
dict(id='rice-awd-2024',source_id='MARD2024',locator='PDF35 / printed27, section4',topic='rice',vi='Sổ tay ĐBSCL 2024 hướng dẫn quản lý nước cho lúa bằng ướt–khô xen kẽ theo giai đoạn. Cần kiểm soát cấp–thoát nước và theo dõi mực nước tại ruộng; mưa tháng không thay được phép đo đó.',en='The 2024 Mekong rice handbook describes stage-specific alternate wetting and drying. It requires water control and field water-level monitoring; monthly rainfall cannot replace those measurements.',tags='AWD rice lúa water irrigation saving tiết kiệm tưới nước'),
dict(id='salinity-scope-2026',source_id='DROUGHT2026',locator='PDF10 / printed8, section2.3',topic='water',vi='Sổ tay hạn mặn 2026–2027 phân lịch lúa theo vùng rủi ro, gồm vùng ven biển và lúa–tôm. Chưa xác nhận Mỹ Thành thuộc các nhóm này; không sao chép lịch hoặc ngưỡng của lúa–tôm cho ruộng.',en='The 2026–2027 drought handbook separates coastal and rice-shrimp risk zones. The target field has not been assigned to those zones; their calendars or thresholds must not be copied automatically.',tags='salinity drought coastal rice shrimp inland scope lịch mặn ven biển vùng phạm vi'),
dict(id='rotation-soil-ctu',source_id='CTU605',locator='PDF1 abstract; PDF3 experimental design',topic='soil',vi='Nghiên cứu CTU về đất lúa ba vụ khảo sát nén dẽ và các hệ luân canh tại Long Khánh/Vĩnh Mỹ. Nó hỗ trợ xem xét cơ chế vật lý đất; chưa chứng minh mức cải thiện ở ruộng Mỹ Thành.',en='The CTU triple-rice soil study examined compaction and rotation systems at Long Khanh/Vinh My. It supports considering soil physical mechanisms, not a quantified benefit for the target field.',tags='compaction soil physical triple rice soil rotation nén dẽ độ bền đoàn lạp luân canh đất ba vụ')]

def crop_intent(q):
 n=norm(q)
 if any(s in n for s in ['baby corn','babycorn','bap non','ngo bao tu']):return 'baby_corn'
 if any(s in n for s in ['mungbean','mung bean','dau xanh']):return 'mungbean'
 return None

class RAG:
 def __init__(self,alpha=.65,rerank=False):
  self.cards=EvidenceRAG().cards
  reg=json.loads((ROOT/'data/raw/v2/agronomy/sources.json').read_text(encoding='utf-8'))
  for c in NEW:
   src=next((s for s in reg if s['id']==c['source_id'] and s['status']=='downloaded'),None)
   if src:self.cards.append(dict(c,source=dict(url=src['url'],sha256=src['sha256'],scope=src['scope']),text_kind='analyst_paraphrase'))
  self.alpha=alpha;self.rerank=rerank
  docs=[norm(c['vi']+' '+c['en']+' '+c['tags']) for c in self.cards]
  self.words=CountVectorizer(token_pattern=r'(?u)\b\w+\b');self.count=self.words.fit_transform(docs).toarray().astype(float)
  self.length=self.count.sum(axis=1);n=len(docs);df=(self.count>0).sum(axis=0);self.idf=np.log(1+(n-df+.5)/(df+.5))
  self.char=TfidfVectorizer(analyzer='char_wb',ngram_range=(3,5));self.mat=self.char.fit_transform(docs)
 def retrieve(self,q):
  query=self.words.transform([norm(q)]).toarray()[0]>0;tf=self.count[:,query]
  bm=(self.idf[query]*tf*2.2/(tf+1.2*(.25+.75*self.length[:,None]/self.length.mean()))).sum(axis=1) if query.any() else np.zeros(len(self.cards))
  ch=(self.mat@self.char.transform([norm(q)]).T).toarray().ravel()
  score=self.alpha*bm/max(bm.max(),1e-10)+(1-self.alpha)*ch/max(ch.max(),1e-10)
  intent=crop_intent(q)
  if intent:
   for i,c in enumerate(self.cards):
    if c['topic'] in ['mungbean','baby_corn'] and c['topic']!=intent:score[i]=-1
  if self.rerank:
   n=norm(q)
   for i,c in enumerate(self.cards):
    if any(s in n for s in ['duration','bao lau','thoi gian','harvest','thu hoach','60','65']) and 'duration' in c['id']:score[i]+=.25
    if any(s in n for s in ['drainage','thoat nuoc','waterlogged']) and 'water' in c['id']:score[i]+=.2
  return [dict(self.cards[i],score=float(score[i])) for i in np.argsort(-score)[:3] if score[i]>0]
 def answer(self,q):
  n=norm(q);hits=self.retrieve(q)
  unsupported=any(s in n for s in ['field ec','ec ruong','ph ruong','guarantee','profit','loi nhuan','ngay mai','tomorrow','ignore previous','ignore all','system prompt','bo qua chi dan','best crop','current crop','yield gain','pesticide','thuoc tru','next month','thang toi','tuan toi'])
  # Bounded knowledge assistant, not an arbitrary-topic chatbot. Structural safety
  # guard added during integration QA; rechecked as regression, not a new test.
  domain=any(s in n for s in ['crop','rice','soil','water','rain','plant','harvest','bean','corn','ph','smap','modis','ndvi','evi','power','t2m','rzmc','sfmc','awd','etc','et0','kc','irrig','drain','salin','rotation','compaction','soy','sesame','luan canh','lua','dat','nuoc','mua','cay','dau','bap','man','phen','gieo','thu hoach','nguon','thuoc','pesticide'])
  unsupported=unsupported or not domain
  abstain=unsupported or not hits
  chosen=[] if abstain else hits[:1]
  return dict(status='insufficient_evidence' if abstain else 'reference_only',answer='Chưa đủ bằng chứng để trả lời cho ruộng; cần thông tin hoặc kiểm chứng bổ sung.' if abstain else chosen[0]['vi'],answer_en='Insufficient evidence for this field.' if abstain else chosen[0]['en'],
   citations=[dict(card_id=c['id'],source_id=c['source_id'],locator=c['locator'],**c['source']) for c in chosen],retrieved=[c['id'] for c in hits],domain_approved=False,generation='constrained extractive; no free-form LLM',location_scope='Mekong/nearby studies with explicit transfer limits')

def evaluate():
 q=json.loads((ROOT/'config/v2-rag.json').read_text(encoding='utf-8'));records=[]
 for alpha in [.35,.65,1.]:
  for rerank in [False,True]:
   rag=RAG(alpha,rerank);scores=[x['id'] in [c['id'] for c in rag.retrieve(x['q'])] for x in q['development']]
   top=[rag.retrieve(x['q'])[0]['id']==x['id'] for x in q['development']]
   records.append(dict(alpha=alpha,rerank=rerank,recall_at3=float(np.mean(scores)),top1=float(np.mean(top))))
 # top1 is a secondary development metric, fixed selection documented in artifact.
 selected=max(records,key=lambda x:(x['recall_at3'],x['top1'],-int(x['rerank']),-abs(x['alpha']-.65)))
 save(OUT/'rag-selection-frozen.json',dict(selected=selected,development=records,selection='development recall@3 then top1, then simpler; final not used',frozen_at_utc=now(),cases_sha256=sha(ROOT/'config/v2-rag.json')))
 rag=RAG(selected['alpha'],selected['rerank']);rows=[]
 for x in q['final']:
  a=rag.answer(x['q']);rows.append(dict(**x,response=a,abstention_correct=(a['status']=='insufficient_evidence')==x.get('abstain',False),recall=None if x.get('abstain') else x['id'] in a['retrieved'],top1=None if x.get('abstain') else x['id'] in [c['card_id'] for c in a['citations']]))
 valid=[x for x in rows if not x.get('abstain')];metrics=dict(n=len(rows),answerable=len(valid),recall_at3=float(np.mean([x['recall'] for x in valid])),top1_evidence_agreement=float(np.mean([x['top1'] for x in valid])),abstention_decisions=float(np.mean([x['abstention_correct'] for x in rows])),citation_provenance_valid=all(c['sha256'] and c['locator'] for x in rows for c in x['response']['citations']),human_faithfulness_evaluated=False,scope=q['scope'],selected=selected)
 save(OUT/'rag-final.json',dict(metrics=metrics,rows=rows));save(OUT/'rag-index.json',rag.cards)
 print(json.dumps(metrics,indent=2))
if __name__=='__main__':evaluate()
