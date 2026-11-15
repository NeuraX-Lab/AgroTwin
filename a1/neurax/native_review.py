"""Finalize Codex-native or Antigravity-native JSON decisions without invoking another LLM."""
from __future__ import annotations
import json
from pathlib import Path

from .core import write_json, timestamp
from .decision import apply_evidence_gates, format_decision, parse_decision
from .project_context import load_project_context


def finalize_native_decision(candidate: Path, run_dir: Path) -> dict:
    """Validate a model-authored candidate against the local deterministic evidence gates.

    This is a file-only operation; it does not call any model or network service.
    The separate scientific Q1/K1 approvals are not implemented, so GO is
    conservatively downgraded when those independent approvals are unavailable.
    """
    out = Path(run_dir).resolve()
    src = Path(candidate).resolve()
    if src == out or not src.is_relative_to(out) or src.suffix.lower() != '.json':
        raise ValueError('Candidate must be a JSON file inside --run-dir')
    if not src.is_file() or src.is_symlink() or src.stat().st_size > 1024 * 1024:
        raise ValueError('Candidate missing, unsafe or larger than 1 MiB')
    if src.name == 'decision.json':
        raise ValueError('Use a separate native_candidate.json, not finalized decision.json')
    fit_file = out / 'fit.json'
    if not fit_file.is_file():
        raise FileNotFoundError('Missing fit.json: first run python -m neurax go --data data/raw --out runs/latest')
    fit = json.loads(fit_file.read_text(encoding='utf-8'))
    ledger_path = out / 'evidence_ledger.json'
    if ledger_path.exists():
        ledger_obj = json.loads(ledger_path.read_text(encoding='utf-8'))
        ledger = ledger_obj.get('sources', [])
        if not isinstance(ledger, list):
            raise ValueError('evidence_ledger.json sources must be a list')
    else:
        ledger = []
        write_json(ledger_path, {'sources': [], 'note': 'No independently recorded source retrievals.'})
    snapshot = load_project_context()['snapshot']
    decision = parse_decision(src.read_text(encoding='utf-8'))
    decision = apply_evidence_gates(decision, fit, ledger, snapshot)
    decision['orchestrator'] = 'external_agent_native'
    write_json(out / 'decision.json', decision)
    (out / 'AI_REVIEW.md').write_text(format_decision(decision), encoding='utf-8')
    write_json(out / 'native_review_manifest.json', {
        'generated_at': timestamp(), 'candidate_file': src.name,
        'finalized_status': decision['status'], 'source_count': len(ledger),
        'independent_scientific_review_completed': False,
        'model_invoked_by_finalizer': False, 'training_executed_by_finalizer': False
    })
    return {'status': decision['status'], 'report': str(out / 'AI_REVIEW.md'),
            'decision': str(out / 'decision.json'),
            'manifest': str(out / 'native_review_manifest.json')}
