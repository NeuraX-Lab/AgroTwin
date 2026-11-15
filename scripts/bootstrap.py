"""Restore exact frozen runtime bytes; never train or overwrite changed files."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'backend'

def digest(body): return hashlib.sha256(body).hexdigest()

def contained(root, name):
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Manifest path escapes its root')
    return path

def restore(offline=False, cache=None):
    manifest = json.loads((BACKEND / 'runtime-manifest.json').read_text(encoding='utf8'))
    assert manifest['selected_system'] == 'v4'
    missing = []
    for item in manifest['files']:
        target = contained(BACKEND, item['path'])
        if target.exists():
            body = target.read_bytes()
        elif 'resource' in item:
            body = contained(BACKEND, item['resource']).read_bytes()
        else:
            cached = contained(cache, item['path']) if cache else None
            if cached and cached.is_file():
                body = cached.read_bytes()
            elif offline:
                missing.append(item['path'])
                continue
            else:
                try:
                    if not item['url'].startswith('https://'):
                        raise ValueError('HTTPS source required')
                    request = urllib.request.Request(item['url'], headers={'User-Agent': 'AgroTwin-reproducibility/1.0'})
                    with urllib.request.urlopen(request, timeout=60) as response:
                        body = response.read(64 * 1024 * 1024 + 1)
                except Exception as error:
                    print(f"UNAVAILABLE: {item['path']}: {type(error).__name__}")
                    missing.append(item['path'])
                    continue
        if len(body) != item['bytes'] or digest(body) != item['sha256']:
            raise ValueError(f"Checksum/size mismatch; no overwrite: {item['path']}. Obtain the frozen source version listed in backend/runtime-manifest.json.")
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
    print(f"Selected v4 runtime restored. Missing external sources: {len(missing)}. No training performed.")
    if missing:
        print('Missing publications cause evidence refusal; they are never replaced by invented evidence.')
        for name in missing: print('  ' + name)
    return missing

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true', help='Restore included resources only; external-source answers may abstain.')
    parser.add_argument('--cache', type=Path, help='Optional existing research checkout; read verified files only, never modify it.')
    args = parser.parse_args()
    try:
        missing = restore(args.offline, args.cache)
    except (OSError, ValueError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 1 if missing and not args.offline else 0

if __name__ == '__main__': sys.exit(main())
