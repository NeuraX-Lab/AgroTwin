"""Deterministic readiness/applicability evaluator; drafts cannot certify crops."""
from datetime import date,timedelta
from . import VERSION
from .inputs import fingerprint,geometry_info

MISSING_TEXT={
    'current_crop':'Confirm the current crop; a historical reference is not the current practice.',
    'previous_crop':'Provide the preceding crop and its source/date.',
    'season':'Confirm the intended sowing/harvest window.',
    'irrigation_access':'Confirm irrigation availability and its seasonal reliability.',
    'drainage_condition':'Check drainage and waterlogging with local expertise.',
}


def scoped_verified(rule,aoi_id):
    return (rule.get('approval_state')=='verified_applicable' and bool(rule.get('reviewer'))
            and bool(rule.get('numeric_reviewer')) and aoi_id in rule.get('scope_aoi_ids',[]))


def evaluate(request,data,catalog):
    farm=request.farm.model_dump();info=geometry_info(request.geometry)
    months=data['months'];qa='fail' if any(r['qa']=='fail' for r in months) else 'warn' if any(r['qa']=='warn' for r in months) else 'pass'
    general_missing=[k for k in MISSING_TEXT if farm.get(k) is None]
    results=[]
    if data['catalog_supported']:
        for rotation in catalog['rotations'][:3]:
            criteria=[];missing=set(general_missing);violations=[];unreviewed=[]
            criteria.append({'criterion_id':'INPUT-COMPLETENESS','kind':'input_completeness_not_crop_suitability',
                             'status':'needs_review' if general_missing else 'pass',
                             'inputs':{k:farm.get(k) for k in MISSING_TEXT},'missing_inputs':general_missing,
                             'evidence_ids':['IMPLEMENTATION-POLICY'],
                             'reason':'Checks whether user context is supplied, not whether the crop is suitable.',
                             'limitation':'Self-reported inputs are not independently verified field observations.'})
            for rule in catalog['rules']:
                if rotation['id'] not in rule['applies_to']:continue
                needed=[k for k in rule['required_inputs'] if farm.get(k) is None]
                missing.update(needed)
                verified=scoped_verified(rule,request.aoi_id)
                status='needs_review';reason='Rule applicability is not approved; draft thresholds were not executed.'
                if not verified:unreviewed.append(rule['id'])
                elif needed:reason='Applicable reviewed rule lacks required inputs.'
                else:
                    # Only explicit reviewed predicates execute; never eval source expressions.
                    predicate=rule.get('predicate',{});value=farm.get(predicate.get('field'))
                    op=predicate.get('operator');expected=predicate.get('value')
                    if op=='eq':ok=value==expected
                    elif op=='in' and isinstance(expected,list):ok=value in expected
                    else:ok=None
                    if ok is None:
                        unreviewed.append(rule['id']);reason='Reviewed rule has no supported computation; needs method review.'
                    else:
                        status='pass' if ok else 'fail';reason='Reviewed predicate evaluated against the stated input.'
                        if not ok and rule.get('kind')=='hard_constraint':violations.append(rule['id'])
                criteria.append({'criterion_id':rule['id'],'kind':rule['kind'],'status':status,
                                 'approval_state':rule.get('approval_state','unknown'),
                                 'inputs':{k:farm.get(k) for k in rule['required_inputs']},'missing_inputs':needed,
                                 'evidence_ids':rule['source_ids'],'reason':reason,'statement':rule['statement'],
                                 'scope':rule.get('scope_aoi_ids',[]),'season':rule.get('season'),
                                 'unit_method':rule.get('unit_method'),'reviewer':rule.get('reviewer'),
                                 'source_refs':rule.get('source_refs',[]),'crop_variety':rule.get('crop_variety'),
                                 'condition':rule.get('condition'),'numeric_reviewer':rule.get('numeric_reviewer'),
                                 'limitation':'Historical observations and model values do not certify this field.'})
            if len(criteria)==1:
                unreviewed.append('NO-APPLICABLE-RULE')
                criteria.append({'criterion_id':'NO-APPLICABLE-RULE','kind':'rule_availability',
                                 'status':'needs_review','inputs':{},'missing_inputs':['applicable_reviewed_rule'],
                                 'evidence_ids':[],'reason':'No rule evidence was supplied for this sequence.',
                                 'limitation':'Input completeness alone cannot establish eligibility.'})
                missing.add('applicable_reviewed_rule')
            eligibility='ineligible' if violations else 'needs_review' if missing or unreviewed or qa!='pass' else 'eligible'
            # No reviewed scoring method or preference weights are supplied in the real catalog.
            results.append({'strategy_id':rotation['id'],'is_current':None,'reference_kind':'historical_reference',
                            'seasons':[{'season_index':i+1,'crop_id':crop,'calendar_window':None} for i,crop in enumerate(rotation['crops'])],
                            'eligibility':eligibility,'score':None,'criteria':criteria,'weights':None,
                            'reasons':[f'Blocked by reviewed constraints: {", ".join(violations)}'] if violations else
                                      ['Additional evidence/applicability review is required.' if eligibility=='needs_review' else 'Reviewed constraints passed; no ranking or outcome guarantee.'],
                            'evidence_ids':sorted({s for c in criteria for s in c['evidence_ids']}),
                            'risks':['Unverified field soil, cultivar, calendar and water management; no yield or water-saving estimate.'],
                            'missing_inputs':sorted(missing),'unreviewed_rules':unreviewed,'scenario_id':None})
    all_missing={k for r in results for k in r['missing_inputs']}
    ordered=[k for k in MISSING_TEXT if k in all_missing]+sorted(all_missing-set(MISSING_TEXT))
    next_actions=[{'input':k,'action':MISSING_TEXT.get(k,f'Provide applicable evidence for {k.replace("_"," ")}, including source/date/method.'),
                   'owner':'farmer_and_agronomic_reviewer'} for k in ordered]
    if not data['catalog_supported']:
        next_actions.append({'input':'regional_crop_catalog','action':'This geometry has no reviewed regional crop catalog. Obtain local crop/season/water evidence; the Mỹ Thành references were not copied here.','owner':'domain_reviewer'})
    if results:next_actions.append({'input':'K1_approval','action':'Request agronomic applicability and independent numerical review before treating references as recommendations.','owner':'accountable_owner_and_domain_review'})
    warnings=[*data['warnings'],'Readiness/evidence-gap analysis, not validated crop advice.','Regional NASA weather is not a measurement at this field.',
              'SOIL-01 is regional historical context; SoilGrids is a model; bench sensors are excluded from this evaluator.']
    if qa!='pass':warnings.append('Climate Q1 has warnings/failures; affected features cannot certify suitability.')
    latest=max((r['date'] for r in months if r['rain'] is not None or r['temp'] is not None),default=None)
    if latest:
        d=date.fromisoformat(latest)
        latest=((date(d.year+1,1,1) if d.month==12 else date(d.year,d.month+1,1))-timedelta(days=1)).isoformat()
    a1={'schema_version':'0.1-proposal','run_id':None,'input_dataset_version':fingerprint({'months':months,'source_sha256':(data['source'] or {}).get('sha256')}),
        'model_version':VERSION,'model_owner':'NeuraX readiness evaluator','generated_at':None,
        'data_as_of':latest,
        'data_mode':'mixed','result_kind':'analysis','status':'partial' if results or data['source'] else 'unavailable',
        'evidence_ids':sorted({s for r in results for s in r['evidence_ids']}),
        'warnings':warnings,'results':results,'evaluation_ref':None,'forecast':None}
    return {'a1':a1,'climate':months,'q1':{'status':qa,'independent_approval':False,'version':'Q1-readiness-1',
            'scope':'coverage, missingness, units and retained source flags; not independent field validation'},
            'next_actions':next_actions,'geometry':info,'source':data['source']}
