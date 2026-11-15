"""Reconstruct available raw POWER and inventory actual local research datasets."""
import json
from pathlib import Path
from .data import load,daily_months
from .inputs import Period
from ..core import sha256_file,write_json


def audit(out=Path('runs/agrotwin-v41-research')):
    out=Path(out);docs=Path('../neurax-docs/nasa-space-apps-2026')
    source_root=docs/'sources/data-audits/my-thanh-cai-lay-2026-11-12'
    original=source_root/'power_daily_2015_2025.json';cache=load('climate.json')
    reconstruction={'raw_available':original.is_file()}
    if original.is_file():
        raw=json.loads(original.read_text(encoding='utf-8'))
        rows=[r for y in range(2015,2026) for r in daily_months(raw,Period(start=f'{y}-01-01',end=f'{y+1}-01-01'))]
        residuals={k:max(abs(a[k]-b[k]) for a,b in zip(rows,cache['months'])) for k in ('temp','rain')}
        reconstruction.update(raw_sha256=sha256_file(original),expected_sha256=cache['source']['sha256'],n_reconstructed=len(rows),
             max_absolute_residual=residuals,passed=sha256_file(original)==cache['source']['sha256'] and len(rows)==132 and max(residuals.values())<1e-5,
             note='Monthly numerical values reconstructed; retained manual source flags are Q1 sidecar, not corrections.')
    inventory=[]
    # Manifest files by identity; do not copy private/source datasets into product Git.
    roots=[docs/'sources/data-audits',Path('neurax/resources/agrotwin'),Path('data/raw'),Path('data/processed')]
    for root in roots:
        if not root.exists():continue
        for p in sorted(root.rglob('*')):
            if p.is_file() and p.suffix.lower() in ('.csv','.json','.geojson','.tif','.nc','.h5'):
                inventory.append({'path':p.as_posix(),'bytes':p.stat().st_size,'sha256':sha256_file(p)})
    value={'schema_version':'dataset-inventory-v41','files':inventory,'raw_to_normalized':reconstruction,
           'source_registry':load('sources.json'),'restrictions':'Provider terms retained in source registry; imagery permission is not inferred from local availability.',
           'availability':{'POWER':'raw daily + curated monthly if paths present',
                           'SoilGrids':'case model context; source sampling does not verify field soil',
                           'Sentinel2':'local research imagery/SCL/metadata listed; not crop labels or current pipeline features',
                           'SOIL01_S4_S5':'published historical evidence, not supervised outcome table',
                           'HLS_MODIS_IMERG':'no configured runtime dataset; not claimed acquired',
                           'H1':'synthetic runtime tests; no authenticated physical log supplied'}}
    write_json(out/'dataset_inventory.json',value)
    if reconstruction.get('raw_available') and not reconstruction.get('passed'):raise ValueError('Raw reconstruction mismatch')
    return value


if __name__=='__main__':print(json.dumps(audit()['raw_to_normalized'],indent=2))
