"""Check the curated submission and execute frozen inference without training."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-all-sources', action='store_true')
    args = parser.parse_args()
    manifest = json.loads((ROOT/'backend/runtime-manifest.json').read_text(encoding='utf8'))
    for item in manifest['files']:
        for key in ['resource', 'path']:
            if key not in item: continue
            path = (ROOT/'backend'/item[key]).resolve()
            assert path.is_relative_to((ROOT/'backend').resolve()), 'Unsafe runtime path'
            if key == 'path' and not path.exists() and 'url' in item: continue
            assert path.is_file(), f'Missing runtime: {item[key]}; run bootstrap first'
            body = path.read_bytes()
            assert len(body) == item['bytes'] and hashlib.sha256(body).hexdigest() == item['sha256'], f'Runtime drift: {item[key]}'
    deck = (ROOT/'presentation/slides/index.html').read_text(encoding='utf8')
    assert len(re.findall(r'<section\b',deck)) == 7, 'Presentation must have seven slides'
    for link in re.findall(r'(?:src|href)="(assets/[^"#]+|static.css)"',deck):
        assert (ROOT/'presentation/slides'/link).is_file(), 'Missing slide asset: '+link
    # Inspect only distributable files. Never print potential secret values.
    files = subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines()
    patterns = [rb'gh[pousr]_[A-Za-z0-9]{30,}', rb'github_pat_[A-Za-z0-9_]{40,}',
                rb'AKIA[0-9A-Z]{16}', rb'sk-proj-[A-Za-z0-9_-]{30,}',
                rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----']
    for name in files:
        path = ROOT/name
        assert not any(part in {'.venv','node_modules','__pycache__','.env'} for part in path.relative_to(ROOT).parts), 'Private/generated file included: '+name
        assert not name.startswith(('backend/data/','backend/runs/','a1/runs/')), 'Raw/generated runtime staged: '+name
        assert path.stat().st_size < 20_000_000, 'Unexpected large file: '+name
        if path.suffix.lower() in {'.png','.pdf','.joblib','.woff','.woff2'}: continue
        body = path.read_bytes()
        assert not any(re.search(pattern,body) for pattern in patterns), 'Possible secret in '+name
    code = '''from scripts.selected_v4_api import SelectedEngine
import json
e=SelectedEngine()
r=e.analyze({'drainage':'poor'},'T2M là gì?')
assert len(r['forecasts'])==6 and r['inference']['prediction_count']==6
assert e.band_override is None and r['selected_system']=='v4'
assert r['rag']['source_bytes_verified']
assert e.rag.answer('What is field EC at this plot?')['status']=='insufficient_evidence'
assert all(o['score'] is None for o in r['decision']['options'])
print(json.dumps(dict(models=len(e.models),months=len(e.m),cards=len(e.rag.cards),verified_sources=sum(e.rag.source_valid(c) for c in e.rag.cards),selected_system='v4')))
'''
    result = subprocess.check_output([sys.executable,'-X','utf8','-c',code],cwd=ROOT/'backend',text=True,encoding='utf8')
    status = json.loads(result)
    if args.require_all_sources: assert status['verified_sources'] == 17, 'External sources incomplete'
    print(json.dumps(dict(files_checked=len(files),slides=7,runtime=status,hardware='NOT_TESTED'),indent=2))

if __name__ == '__main__': main()
