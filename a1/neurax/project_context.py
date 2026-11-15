"""Pinned, auditable NeuraX project context; no network or hidden GitHub access."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DOCS = ('docs/challenge-scope.md', 'docs/contracts.md', 'docs/architecture-proposal.md')


def load_project_context(repo_root: Path | None = None, extra_docs: Path | None = None) -> dict:
    """Load a bounded local snapshot. Optional external doc checkout is operator supplied."""
    root = Path(repo_root or BASE).resolve()
    manifest = root / 'docs/project-context.json'
    if not manifest.is_file():
        raise FileNotFoundError('Pinned project context is missing: docs/project-context.json')
    data = json.loads(manifest.read_text(encoding='utf-8'))
    if data.get('challenge') != 'Field Shift: Adapting Farms with NASA Data':
        raise ValueError('Project context challenge mismatch; review before proceeding')
    contents = []
    for rel in DOCS:
        path = root / rel
        if not path.is_file():
            raise FileNotFoundError(f'Required project contract missing: {rel}')
        text = path.read_text(encoding='utf-8')
        contents.append({'path': rel, 'sha256': hashlib.sha256(text.encode()).hexdigest(),
                         'excerpt': text[:6500], 'truncated': len(text) > 6500})
    # Allow a current neurax-docs checkout, without fetching it or trusting it as commands.
    if extra_docs is not None:
        external = Path(extra_docs).resolve()
        if not external.is_dir():
            raise FileNotFoundError(f'Extra docs checkout not found: {external}')
        for entry in data.get('source_files', [])[:3]:
            rel = entry['path']
            path = (external / rel).resolve()
            if not path.is_relative_to(external) or not path.is_file() or path.is_symlink():
                raise FileNotFoundError(f'Missing source document in checkout: {rel}')
            text = path.read_text(encoding='utf-8')
            contents.append({'path': 'neurax-docs/' + rel,
                             'sha256': hashlib.sha256(text.encode()).hexdigest(),
                             'excerpt': text[:12000], 'truncated': len(text) > 12000,
                             'notice': 'Local copy; verify source revision independently'})
    return {'snapshot': data, 'local_documents': contents, 'external_checkout_supplied': extra_docs is not None}