"""Offline, immutable evidence snapshots for shared inspection; not A1 ranking.

The wrapper is a draft integration format. It does not approve K1/Q1, train a
model, infer a current rotation or expose a network service.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import tempfile
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .core import timestamp, write_json

SCHEMA = 'agrotwin-evidence-bundle/0.1-draft'
FILES = {'climate.json', 'soil.json', 'imagery.json', 'references.json', 'reviews.json', 'sources.json'}
UNAVAILABLE = ('rotation_ranking', 'scenario_effects', 'forecast', 'live_hardware')


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def _json(data):
    return json.loads(data, object_pairs_hook=_object,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON number')))


def _number(value):
    if value is None or value == '':
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('Nonfinite feature value')
    return result


def _climate(text, year, manifest):
    rows, keys = [], set()
    required = {'region_id', 'period_start', 'period_end', 'precip_sum_mm', 'air_temp_mean_c',
                'precip_coverage', 'temp_coverage', 'qa_status'}
    reader = csv.DictReader(io.StringIO(text))
    if not required <= set(reader.fieldnames or []):
        raise ValueError('Missing D1 climate columns')
    for raw in reader:
        start, end = date.fromisoformat(raw['period_start']), date.fromisoformat(raw['period_end'])
        expected_end = date(start.year+1, 1, 1) if start.month == 12 else date(start.year, start.month+1, 1)
        if start.day != 1 or end != expected_end:
            raise ValueError('D1 must use calendar months with exclusive period_end')
        key = (raw['region_id'], start)
        if key in keys:
            raise ValueError('Duplicate D1 region/month key')
        keys.add(key)
        if raw['region_id'] != manifest['region_id']:
            raise ValueError('D1 entity does not match its manifest')
        row = {k:raw[k] for k in ('region_id', 'period_start', 'period_end', 'qa_status')}
        for k in ('precip_sum_mm', 'air_temp_mean_c', 'precip_coverage', 'temp_coverage'):
            row[k] = _number(raw[k])
        for value, coverage in [('precip_sum_mm', 'precip_coverage'), ('air_temp_mean_c', 'temp_coverage')]:
            c = row[coverage]
            if c is not None and not 0 <= c <= 1:
                raise ValueError('Coverage outside 0..1')
            if row[value] is not None and c != 1:
                raise ValueError('Incomplete month cannot have a complete monthly feature')
        if row['precip_sum_mm'] is not None and row['precip_sum_mm'] < 0:
            raise ValueError('Negative precipitation')
        if start.year == year:
            rows.append(row)
    if not rows:
        raise ValueError('No D1 rows in requested year')
    return sorted(rows, key=lambda x:x['period_start'])


def build_evidence_bundle(run_dir: Path, coverage_dir: Path, review_dir: Path,
                          case_dir: Path, out: Path, year: int = 2025) -> dict:
    roots = {k:Path(v).resolve() for k,v in [('run',run_dir),('coverage',coverage_dir),
                                          ('review',review_dir),('case',case_dir)]}
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError('Choose a new output directory; evidence bundles are immutable')
    if any(out == p or p in out.parents for p in roots.values()):
        raise ValueError('Output must be separate from input directories')
    if not 1900 <= year <= 2200:
        raise ValueError('Unsupported analysis year')
    fingerprints = {}

    def read(root, name, as_json=True):
        base = roots[root]; path = base/name
        if path.is_symlink() or not path.resolve().is_relative_to(base) or not path.is_file():
            raise ValueError(f'Input missing or unsafe: {root}/{name}')
        if path.stat().st_size > 8*1024*1024:
            raise ValueError(f'Input exceeds metadata size limit: {root}/{name}')
        b = path.read_bytes()
        fingerprints[f'{root}/{name}'] = _hash(b)
        return _json(b.decode('utf-8-sig')) if as_json else b.decode('utf-8-sig')

    d1 = read('run','D1/manifest.json')
    power = read('run','power-qa.json')
    soil = read('run','soil-qa.json')
    coverage = read('coverage','coverage-summary.json')
    k1 = read('review','k1-rule-candidates.json')
    review = read('review','bich-review-reconciliation.json')
    evidence = read('run','source-ledger.json')
    geometry = read('case','study-block.geojson')
    case = read('case','study-block-manifest.json')['properties']
    features = _climate(read('run','D1/features.csv',False),year,d1)
    if d1['source_sha256'] != power['source_sha256']:
        raise ValueError('Climate QA and D1 source mismatch')
    if power['header']['time_standard'] != 'UTC':
        raise ValueError('Expected checked UTC climate input')
    if power['parameters']['PRECTOTCORR']['units'] != 'mm/day' or power['parameters']['T2M']['units'] != 'C':
        raise ValueError('Unrecognized climate units')
    if coverage['geometry_sha256'] != fingerprints['case/study-block.geojson']:
        raise ValueError('Imagery belongs to a different geometry version')
    if not coverage['monthly'] or any(not x['month'].startswith(str(year)+'-') for x in coverage['monthly']):
        raise ValueError('Imagery and climate analysis years differ')
    if k1['area_id'] != case['id'] or k1['area_id'] != 'MT-BLOCK-01':
        raise ValueError('Review and case IDs do not match supported case')
    if geometry['features'][0]['properties']['id'] != case['id']:
        raise ValueError('Geometry and case IDs differ')
    if len(soil['point_lon_lat']) != 2 or len(case['center_lon_lat']) != 2 or any(
            abs(a-b)>1e-7 for a,b in zip(soil['point_lon_lat'],case['center_lon_lat'])):
        raise ValueError('Soil sample point differs from case centroid')
    source_ids = {s['id'] for s in k1['sources']}
    if any(not set(rule['source_ids']) <= source_ids for rule in k1['rules']):
        raise ValueError('Rule cites an unknown source ID')
    if not any(x['submission_sha256'] == review['attachments'][0]['sha256'] for x in k1['submitted_reviews']):
        raise ValueError('Rule draft and submitted-review fingerprints differ')

    warnings = list(dict.fromkeys([
        'Evidence-inspection snapshot, not an approved A1 crop-ranking result.',
        'Regional weather, modeled soil and satellite pixels are not measured field conditions.',
        'Current rotation, water management and crop-response rules remain unknown.',
        'Initial evidence review received; independent QA and rule applicability approval are pending.',
        *d1.get('warnings',[]), *soil.get('limits',[]), *coverage.get('limitations',[])]))
    identities = {}
    for record in evidence:
        href = record.get('url') or record.get('source_href')
        if href:
            # Avoid forwarding local paths, source attachment contents or access signatures.
            parsed = urlsplit(href)
            if parsed.scheme not in ('https', 'http') or not parsed.netloc or parsed.username or parsed.password:
                raise ValueError('Only public HTTP(S) source URLs without credentials may be included')
            signed_keys = {'sig', 'signature', 'x-amz-signature', 'x-goog-signature'}
            if signed_keys.intersection(k.lower() for k in parse_qs(parsed.query)):
                raise ValueError('Temporary signed URL cannot be included in a bundle')
            identities[(href,record['sha256'])] = {
                'url':href,'sha256':record['sha256'],
                'retrieved_at_utc':record.get('retrieved_at_utc'),
                'method':record.get('method','downloaded public source or metadata')}
    refs = []
    for rot in k1['rotations']:
        if rot.get('is_current') is not None:
            raise ValueError('This inspection producer cannot certify a current rotation')
        rules = [r for r in k1['rules'] if rot['id'] in r['applies_to']]
        refs.append({'reference_id':rot['id'], 'crops':rot['crops'], 'kind':'historical_reference',
                     'is_current':None, 'field_applicability':'unknown', 'score':None,
                     'evidence_ids':[s for s in ('S4','S5') if s in source_ids],
                     'rule_candidate_ids':[r['id'] for r in rules],
                     'missing_inputs':sorted({x for r in rules for x in r['required_inputs']}),
                     'warning':'Reference sequence; no crop suitability or current-practice claim.'})
    payloads = {
        'climate.json':{'entity_id':d1['region_id'],'source_kind':'gridded_weather_estimate',
                        'spatial_support':'regional grid context, not field-level measurement',
                        'native_grid_degrees':None,
                        'native_grid_note':'Exact per-variable native grid not supplied by the consumed D1 manifest; consult product metadata.',
                        'time_standard':'UTC','units':{'precip_sum_mm':'mm/month','air_temp_mean_c':'C'},
                        'rows':features,'data_as_of':str(date.fromisoformat(features[-1]['period_end'])-timedelta(days=1)),
                        'source_sha256':d1['source_sha256'],
                        'source_quality_flags':d1['source_metadata'].get('quality_flags',[]),
                        'warnings':['Monthly QA pass means complete coverage, not independent scientific approval.']},
        'soil.json':soil,
        'imagery.json':coverage,
        'references.json':{'references':refs,'ranking_available':False,'scenario_effects_available':False},
        'reviews.json':{'initial_evidence_review_received':True,'reconciled_row_count':review['row_count'],
                        'rule_draft_version':k1['draft_version'],'rule_approval_consumed':False,
                        'independent_Q1_approval_consumed':False,
                        'rule_candidates':k1['rules'],'rule_source_descriptions':k1['sources'],
                        'numeric_claims_not_adopted':review['unsupported_numeric_claims']},
        'sources.json':{'inputs':fingerprints,'retrieved_sources':list(identities.values()),
                        'case':{'id':case['id'],'geometry':geometry,'center_lon_lat':case['center_lon_lat'],
                                'area_ha_approx':case['area_ha_approx'],'status':case['status']},
                        'license_notes':[f'Contains modified Copernicus Sentinel data ({year}).',
                                         'ISRIC SoilGrids CC-BY-4.0; retain attribution and uncertainty.',
                                         'CTU papers are cited; their full texts are not included.']}}
    key = {'schema':SCHEMA,'year':year,'inputs':fingerprints,'producer_sha256':_hash(Path(__file__).read_bytes())}
    bundle_id = 'evidence-'+_hash(json.dumps(key,sort_keys=True).encode())[:20]
    capabilities = {name:{'status':'available','purpose':'inspection_only'} for name in
                    ['climate_inspection','soil_context','imagery_coverage','reference_rotations','evidence_review']}
    if len(features) != 12:
        capabilities['climate_inspection']['status']='partial'
        warnings.append('Selected year has missing monthly rows; absent months were not zero-filled.')
    if any(r[k] is None for r in features for k in ('precip_sum_mm', 'air_temp_mean_c')):
        capabilities['climate_inspection']['status']='partial'
        warnings.append('Some monthly climate values are unavailable; nulls were preserved.')
    if coverage['failures']:
        capabilities['imagery_coverage']['status']='partial'
        warnings.append('Some imagery access checks failed; do not interpret them as cloudy observations.')
    for name in UNAVAILABLE:
        capabilities[name]={'status':'unavailable','reason':'No reviewed scientific producer/artifact consumed for this capability.'}
    manifest = {'bundle_schema_version':SCHEMA,'bundle_id':bundle_id,'generated_at_utc':timestamp(),
                'artifact_kind':'shared_evidence_inspection_snapshot_not_A1','status':'partial','data_mode':'mixed',
                'analysis_area_id':case['id'],'period':{'start':f'{year}-01-01','end_exclusive':f'{year+1}-01-01'},
                'capabilities':capabilities,'scientific_contracts':{
                    'D1':{'state':'partial','reason':'Normalized climate checked technically; source warning and review pending.'},
                    'Q1':{'state':'partial','independent_review_approved':False},
                    'K1':{'state':'unavailable','reason':'Only a reconciled review draft, not approved runtime rules.'},
                    'A1':{'state':'unavailable','artifact':None},
                    'E1':{'state':'unavailable','artifact':None},'H1':{'state':'unavailable','artifact':None}},
                'producer':{'module':'neurax.evidence_bundle','sha256':key['producer_sha256']},
                'warnings':warnings,'files':{}}
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.neurax-bundle-',dir=out.parent) as tmp:
        stage = Path(tmp)
        for name,value in payloads.items():
            write_json(stage/name,value)
            manifest['files'][name]={'sha256':_hash((stage/name).read_bytes())}
        write_json(stage/'manifest.json',manifest)
        validate_evidence_bundle(stage)
        stage.rename(out)
    return {'bundle_id':bundle_id,'out':str(out),'status':'partial','files':len(FILES),
            'ranking_available':False,'warnings':len(warnings)}


def validate_evidence_bundle(path: Path) -> dict:
    path = Path(path).resolve()
    manifest = _json((path/'manifest.json').read_text(encoding='utf-8'))
    if manifest['bundle_schema_version'] != SCHEMA or set(manifest['files']) != FILES:
        raise ValueError('Unsupported bundle version or payload list')
    for name,record in manifest['files'].items():
        target = path/name
        if target.is_symlink() or not target.is_file() or _hash(target.read_bytes()) != record['sha256']:
            raise ValueError(f'Payload integrity failure: {name}')
    for name in UNAVAILABLE:
        if manifest['capabilities'][name]['status'] != 'unavailable':
            raise ValueError('Inspection bundle cannot enable scientific capabilities')
    for contract in ('K1','A1','E1','H1'):
        if manifest['scientific_contracts'][contract]['state'] != 'unavailable':
            raise ValueError('Inspection bundle cannot certify scientific contracts')
    if manifest['scientific_contracts']['A1']['artifact'] is not None:
        raise ValueError('Inspection bundle is not an A1 producer')
    if manifest['scientific_contracts']['Q1']['independent_review_approved']:
        raise ValueError('Independent approval cannot be supplied by this producer')
    review = _json((path/'reviews.json').read_text(encoding='utf-8'))
    if review['rule_approval_consumed'] or review['independent_Q1_approval_consumed']:
        raise ValueError('This producer does not consume scientific approvals')
    refs = _json((path/'references.json').read_text(encoding='utf-8'))
    if refs['ranking_available'] or refs['scenario_effects_available']:
        raise ValueError('Reference inspection cannot enable comparison')
    if any(x['score'] is not None or x['is_current'] is not None or x['field_applicability'] != 'unknown'
           for x in refs['references']):
        raise ValueError('Unsupported field conclusion in historical references')
    return {'valid':True,'bundle_id':manifest['bundle_id'],'validated_scope':'hashes_and_inspection_boundaries_not_scientific_approval'}
