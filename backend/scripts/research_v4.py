"""Same corpus/retriever, evidence-sufficiency and source-byte integrity gates."""
from pathlib import Path
import argparse
import copy
import json
import re
import sys
import time
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import research_v3 as r
from v2_rag import RAG
from research_rag import norm
OUT=ROOT/'runs/research-v4-refined'
REPORT=ROOT/'reports/v4/evidence/refined'
STOP=set('a an the of in on at to for and or is are was were be been does do did can could how what which why when where with by from as it its this that these those than my your has have not directly versus right procedure steps'.split())
SYNONYMS={'variety':'cultivar','days':'day','requires':'require','requirements':'require','samples':'sample','replicates':'replicate','measurements':'measurement','measured':'measure','measures':'measure','planting':'sowing','harvesting':'harvest','flooding':'waterlogging'}


def tokens(q):
    text=norm(q).replace('crop coefficient','kc').replace('reference evapotranspiration','et0')
    return {SYNONYMS.get(w,w) for w in re.findall(r'[a-z]+\d*|\d+',text) if w not in STOP and w not in {'equals','times'}}


class EvidenceGate:
    def __init__(self,threshold=.55,sufficiency=True,integrity=True):
        self.base=RAG()
        self.cards=json.loads((r.OUT/'corpus-frozen.json').read_text(encoding='utf-8'))
        if self.base.cards!=self.cards:raise ValueError('v2 corpus drift; evaluation corpus must stay frozen')
        self.threshold=threshold;self.sufficiency=sufficiency;self.integrity=integrity
        manifest=json.loads((r.OUT/'data-manifest.json').read_text(encoding='utf-8'))
        self.paths={e['sha256']:ROOT/e['path'] for e in reversed(manifest['files'])}
        self.card_tokens={c['id']:tokens(c['vi']+' '+c['en']+' '+c['tags']) for c in self.cards}

    def source_valid(self,c):
        p=self.paths.get(c['source']['sha256'])
        return bool(p and p.is_file() and r.sha(p)==c['source']['sha256'])

    def answer(self,q):
        begin=time.perf_counter();a=self.base.answer(q);reason='v2_policy' if a['status']=='insufficient_evidence' else None
        hit=next((c for c in self.cards if a['citations'] and c['id']==a['citations'][0]['card_id']),None)
        words=tokens(q);coverage=0 if hit is None or not words else len(words & self.card_tokens[hit['id']])/len(words)
        # Dynamic measurements need sensors/observations absent from this corpus.
        dynamic=bool(re.search(r'\b(now|current|today|sensor)\b',norm(q)))
        if self.sufficiency and (coverage<self.threshold or dynamic):reason='insufficient_query_support'
        if self.integrity and hit is not None and not self.source_valid(hit):reason='source_integrity_failure'
        if reason:
            a.update(status='insufficient_evidence',answer='Chưa đủ bằng chứng đã kiểm chứng để trả lời câu hỏi này cho ruộng.',
                     answer_en='Insufficient verified evidence for this question.',citations=[])
        a.update(query_support_fraction=coverage,abstention_reason=reason,
                 source_bytes_verified=bool(not reason and hit and self.integrity),generation='constrained extractive; query support + source integrity',
                 latency_ms=(time.perf_counter()-begin)*1000)
        return a


def assess(engine,cases):
    rows=[]
    for case in cases:
        a=engine.answer(case['q']);abstain=a['status']=='insufficient_evidence'
        literal=all(a['answer']==c['vi'] for c in engine.cards if a['citations'] and c['id']==a['citations'][0]['card_id']) if not abstain else True
        rows.append(dict(**case,response=a,correct_abstention=abstain==case.get('abstain',False),
                         evidence_agreement=None if case.get('abstain') else bool(a['citations'] and a['citations'][0]['card_id']==case['id']),literal_support=literal))
    positives=[x for x in rows if not x.get('abstain')];negatives=[x for x in rows if x.get('abstain')]
    return dict(metrics=dict(n=len(rows),answerable=len(positives),unanswerable=len(negatives),
         answerable_evidence_agreement=float(np.mean([x['evidence_agreement'] for x in positives])) if positives else None,
         retrieval_recall_at3=float(np.mean([x['id'] in x['response']['retrieved'] for x in positives])) if positives else None,
         correct_abstention=float(np.mean([x['correct_abstention'] for x in negatives])) if negatives else None,
         overall_correct=float(np.mean([x['correct_abstention'] and x['evidence_agreement'] is not False for x in rows])),
         literal_support=all(x['literal_support'] for x in rows),
         verified_citation_fraction=float(np.mean([x['response'].get('source_bytes_verified',False) for x in rows if x['response']['citations']])) if any(x['response']['citations'] for x in rows) else None,
         expert_groundedness_evaluated=False),rows=rows)


def develop():
    if (OUT/'selection-frozen.json').exists():raise FileExistsError('Do not overwrite frozen RAG selection')
    r.verify_manifest()
    cases=json.loads((ROOT/'config/v4-rag-evaluation.json').read_text(encoding='utf-8'))
    old=json.loads((ROOT/'config/v2-rag.json').read_text(encoding='utf-8'))
    dev=old['development']+cases['development'];regression=old['final']
    records=[]
    baseline=assess(RAG(),dev);r.save(REPORT/'baseline-development.json',baseline)
    for threshold in [.4,.55,.7]:
        gate=EvidenceGate(threshold);score=assess(gate,dev);reg=assess(gate,regression)
        records.append(dict(threshold=threshold,development=score['metrics'],exposed_regression=reg['metrics']))
        r.save(REPORT/f'development-{threshold}.json',score)
        r.save(REPORT/f'exposed-regression-{threshold}.json',reg)
    # Existing final is explicitly exposed regression; it guards regressions but
    # is not marketed as an independent test. New final remains unopened.
    feasible=[x for x in records if x['exposed_regression']['answerable_evidence_agreement']==1. and x['exposed_regression']['correct_abstention']==1.]
    chosen=max(feasible or records,key=lambda x:(x['development']['overall_correct'],-x['threshold']))
    gate=EvidenceGate(chosen['threshold']);ablations={}
    for label,suff,integrity in [('full',True,True),('no_sufficiency',False,True),('no_integrity',True,False)]:
        ablations[label]=assess(EvidenceGate(chosen['threshold'],suff,integrity),dev)['metrics']
    # Simulate a missing/mismatched source by changing a copied card hash, never
    # touching actual raw source files. The corpus used for main metrics is fixed.
    corrupted=EvidenceGate(chosen['threshold']);card=next(c for c in corrupted.cards if c['id']=='mungbean-water')
    card['source']['sha256']='0'*64
    query='Does mungbean need irrigation and drainage?'
    fault=corrupted.answer(query)
    unguarded=EvidenceGate(chosen['threshold'],integrity=False)
    next(c for c in unguarded.cards if c['id']=='mungbean-water')['source']['sha256']='0'*64
    fault_no_gate=unguarded.answer(query)
    r.save(REPORT/'ablation.json',dict(development=ablations,source_fault=dict(guarded=fault,without_integrity=fault_no_gate),
                                    limitation='Authored support check; no semantic entailment or independent agronomy audit'))
    ledger=dict(selected=chosen,promoted=bool(feasible),records=records,ml_selection_sha256=r.sha(r.OUT/'selection-frozen.json'),
                corpus_sha256=r.sha(r.OUT/'corpus-frozen.json'),cases_sha256=r.sha(ROOT/'config/v4-rag-evaluation.json'),
                final_used=False,selection_utc=__import__('pandas').Timestamp.now(tz='UTC').isoformat())
    r.save(OUT/'selection-frozen.json',ledger);r.save(REPORT/'selection-frozen.json',ledger)
    print(json.dumps(dict(baseline=baseline['metrics'],chosen=chosen,ablations=ablations),indent=2))


def final():
    if (OUT/'final-opened.json').exists():raise FileExistsError('Final already evaluated')
    ledger=json.loads((OUT/'selection-frozen.json').read_text(encoding='utf-8'))
    assert ledger['cases_sha256']==r.sha(ROOT/'config/v4-rag-evaluation.json')
    cases=json.loads((ROOT/'config/v4-rag-evaluation.json').read_text(encoding='utf-8'))['final']
    r.save(OUT/'final-opened.json',dict(selection_sha256=r.sha(OUT/'selection-frozen.json'),opened_utc=__import__('pandas').Timestamp.now(tz='UTC').isoformat()))
    result=assess(EvidenceGate(ledger['selected']['threshold']),cases)
    baseline=assess(RAG(),cases)
    r.save(REPORT/'final.json',dict(selected=result,baseline=baseline,independence='Separate authored cases; not external/expert gold'))
    print('RAG final recorded; no threshold changes')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['develop','final']);p.add_argument('--out',type=Path);args=p.parse_args()
    if args.out:
        OUT=args.out.resolve();REPORT=OUT/'reports'
    globals()[args.command]()
