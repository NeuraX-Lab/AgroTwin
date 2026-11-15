"""Immutable local runs and content-keyed response cache; no network service binding."""
import copy
import json
import re
import threading
from pathlib import Path

from ..core import timestamp,write_json
from . import VERSION
from .data import acquire,load
from .engine import evaluate
from .inputs import AnalysisInput,fingerprint,geometry_info

LOCK=threading.RLock()


def analyze(request:AnalysisInput,store:Path):
    store=Path(store);catalog=load('catalog.json');case=load('case.json');registry=load('sources.json')
    code_hash=fingerprint({name:(Path(__file__).parent/name).read_text(encoding='utf-8') for name in ('inputs.py','data.py','engine.py','service.py')})
    data=acquire(request,store)
    material=request.model_dump(mode='json')
    material['geometry']={'geometry_hash':geometry_info(request.geometry)['geometry_hash']}
    material.pop('source_mode') # source bytes/version, not acquisition preference, determine scientific identity
    key=fingerprint({'input':material,'data':{'months':data['months'],'source_sha256':(data['source'] or {}).get('sha256')},
                     'catalog':catalog,'registry':registry,'case':case,'evaluator':VERSION,'implementation':code_hash})
    run_id='a1-'+key[:24];path=store/'results'/(run_id+'.json')
    with LOCK:
        if path.exists():
            result=json.loads(path.read_text(encoding='utf-8'));mode='offline' if request.source_mode=='offline' else 'cached'
        else:
            result=evaluate(request,data,catalog);now=timestamp()
            # Observation/science identity excludes wall-clock and acquisition warnings.
            # The complete content key includes input, source, catalog, registry and code.
            scientific=copy.deepcopy(result)
            scientific['a1'].pop('generated_at',None)
            scientific['a1'].pop('run_id',None)
            scientific['a1'].pop('warnings',None)
            scientific.pop('source',None)
            scientific_sha=fingerprint({'material_key':key,'evaluation':scientific})
            result['a1'].update(run_id=run_id,generated_at=now)
            result['inputs']=request.model_dump(mode='json')
            result['sources']=registry['sources']
            result['case_context']=case['properties'] if data['catalog_supported'] else None
            result['soil_context']=case['soil_context'] if data['catalog_supported'] else None
            result['sidecar']={'schema_version':'agrotwin-orchestration-1','input_hash':fingerprint(material),
                               'geometry_hash':geometry_info(request.geometry)['geometry_hash'],'scientific_payload_sha256':scientific_sha,
                               'evaluator_version':VERSION,'implementation_sha256':code_hash,'K1_version':catalog['version'],'K1_sha256':fingerprint(catalog),
                               'D1_version':result['a1']['input_dataset_version'],'computed_at':now,'observed_period':request.period.model_dump(mode='json'),
                               'retrieved_at':(data['source'] or {}).get('retrieved_at'),'source_sha256':(data['source'] or {}).get('sha256'),
                               'source_acquisition':(data['source'] or {}).get('acquisition','unavailable'),
                               'execution_mode':'computed','cache_hit':False,'catalog_supported':data['catalog_supported']}
            write_json(path,result);mode='computed'
        response=copy.deepcopy(result)
        response['sidecar'].update(execution_mode=mode,cache_hit=mode!='computed',served_at=timestamp(),
                                   acquisition_warnings=data['warnings'])
        return response


def read_run(run_id,store):
    if not re.fullmatch(r'a1-[a-f0-9]{24}',run_id):raise ValueError('Invalid run ID')
    path=Path(store)/'results'/(run_id+'.json')
    return json.loads(path.read_text(encoding='utf-8'))
