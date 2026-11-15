"""Validate AI decision objects and gate unsupported claims before handoff."""
from __future__ import annotations
import json
import re

REQUIRED = ('status', 'dataset_interpretation', 'quality_findings', 'project_fit',
            'product_options', 'recommended_product', 'model_candidates',
            'interfaces', 'team_handoffs', 'evidence_ids', 'blockers', 'next_actions')
STATUS = {'go', 'partial', 'no_go'}
MODEL_GATE = {'ready', 'conditional', 'blocked', 'not_needed'}


def parse_decision(raw: str) -> dict:
    text = (raw or '').strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text, count=1, flags=re.I)
        text = re.sub(r'\s*```$', '', text, count=1)
    try:
        obj = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise ValueError('AI did not return parseable JSON decision') from exc
    if not isinstance(obj, dict):
        raise ValueError('AI decision must be a JSON object')
    missing = [key for key in REQUIRED if key not in obj]
    if missing:
        raise ValueError('AI decision missing keys: ' + ', '.join(missing))
    if obj['status'] not in STATUS:
        raise ValueError('Invalid decision status')
    if not isinstance(obj['project_fit'], dict) or not isinstance(obj['dataset_interpretation'], dict):
        raise ValueError('Project fit and dataset interpretation must be objects')
    if not isinstance(obj['recommended_product'], str) or not obj['recommended_product'].strip():
        raise ValueError('Missing recommended product')
    for key in ('quality_findings','product_options','model_candidates','team_handoffs',
                'evidence_ids','blockers','next_actions'):
        if not isinstance(obj[key], list):
            raise ValueError(key + ' must be an array')
    if not isinstance(obj['interfaces'], dict):
        raise ValueError('interfaces must be an object')
    if any(k not in obj['interfaces'] for k in ('D1','Q1','K1','A1','E1','H1')):
        raise ValueError('interfaces must cover D1/Q1/K1/A1/E1/H1')
    for model in obj['model_candidates']:
        if not isinstance(model, dict) or model.get('train_gate') not in MODEL_GATE:
            raise ValueError('Model candidate must specify train_gate')
        necessary=('task','target','inputs','output','baseline','candidate','hyperparameters',
                   'validation','metrics','resource_plan')
        if any(k not in model for k in necessary):
            raise ValueError('Model candidate missing required modeling contract fields')
    return obj


def apply_evidence_gates(obj: dict, fit: dict, ledger: list[dict], snapshot: dict) -> dict:
    """Prevent a persuasive LLM answer from substituting for independently reviewed K1/Q1."""
    blockers = [str(x) for x in obj['blockers']]
    flags = []
    fit_text = ' '.join(fit.get('gaps', [])).lower()
    source_verified = 'no nasa provenance' not in fit_text and \
        'nasa provider claimed but source marked unverified' not in fit_text
    if not source_verified:
        flags.append('NASA source/version not independently verified')
    # No hand-approved Q1/K1 artifact or signed crop rules is currently consumed by this runtime.
    flags.append('Independent Q1 data quality approval not supplied to decision engine')
    flags.append('Independent K1 crop/soil/season review not supplied to decision engine')
    if snapshot.get('still_unconfirmed'):
        flags.append('Pinned project snapshot still lists unresolved evidence or integration items')
    refs = [x for x in obj['evidence_ids'] if isinstance(x, str)]
    found = {x['id'] for x in ledger if 'id' in x}
    invalid = [x for x in refs if x not in found]
    if invalid:
        flags.append('AI mentioned source IDs that were never retrieved: ' + ', '.join(invalid[:8]))
    if obj['status'] == 'go':
        obj['status'] = 'partial'
        flags.append('GO downgraded: no independently approved crop-rotation and QA evidence')
    not_observed = 'dataset not explicitly marked observed' in fit_text
    for model in obj['model_candidates']:
        if model['train_gate'] == 'ready':
            model['train_gate'] = 'blocked' if not_observed else 'conditional'
            flags.append('Training-ready claim downgraded until observed data, explicit QA, provenance and leakage review')
    obj['blockers'] = list(dict.fromkeys(blockers + flags))
    obj['evidence_guardrails'] = flags
    obj['source_ids_validated'] = [x for x in refs if x in found]
    obj['unverified_source_ids'] = invalid
    obj['independent_review_required'] = True
    obj['training_executed'] = False
    obj['product_implemented'] = False
    return obj


def format_decision(obj: dict) -> str:
    def item(v):
        if isinstance(v, str): return v
        return json.dumps(v, ensure_ascii=False)
    result = ['# NeuraX AI decision — requires review', '',
              '> AI-generated candidate analysis; not a crop or model accuracy certificate.', '',
              '**Decision:** ' + obj['status'].upper(), '',
              '## Dataset meaning', item(obj['dataset_interpretation']), '',
              '## Quality issues']
    result += ['- '+item(v) for v in obj['quality_findings']] or ['- No issues independently reviewed']
    result += ['', '## AgroTwin / Field Shift fit',item(obj['project_fit']), '',
               '## Preferred product',obj['recommended_product'],'', '## Alternative products']
    result += ['- '+item(x) for x in obj['product_options']]
    result += ['', '## Models and training gates']
    result += ['- '+item(x) for x in obj['model_candidates']]
    result += ['', '## Versioned API and hardware interfaces',item(obj['interfaces']),
               '', '## Team handoffs']
    result += ['- '+item(x) for x in obj['team_handoffs']]
    result += ['', '## Sources actually recorded']
    result += ['- '+x for x in obj.get('source_ids_validated',[])] or ['- No retrieved public sources']
    result += ['', '## Blockers and validation requirements']
    result += ['- '+x for x in obj['blockers']]
    result += ['', '## Next actions']
    result += ['- '+item(x) for x in obj['next_actions']]
    result += ['', '_No training, product deployment, ESP32 verification or independent scientific approval was performed by this report._','']
    return '\n'.join(result)