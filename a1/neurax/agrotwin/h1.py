"""Local H1 event history and conservative monitoring features; no field auto-approval."""
from datetime import datetime,timezone
from pathlib import Path
import json
import math
import threading
from typing import Literal
from pydantic import BaseModel,Field,ConfigDict,field_validator
from .inputs import fingerprint
from ..core import write_json,timestamp

LOCK=threading.RLock()


class Event(BaseModel):
    model_config=ConfigDict(extra='ignore')
    device_id:str=Field(min_length=1,max_length=64)
    event_id:str|None=Field(default=None,max_length=120)
    timestamp_utc:datetime
    event_type:str=Field(min_length=1,max_length=64)
    value:float|None=None
    unit:str|None=Field(default=None,max_length=40)
    quality:str=Field(default='unverified',max_length=30)
    data_mode:str=Field(pattern='^(simulated|observed|replay)$')
    delivery_mode:Literal['live','replay']|None=None
    calibration_id:str|None=Field(default=None,max_length=120)
    source_context:str|None=Field(default=None,max_length=200)

    @field_validator('timestamp_utc')
    @classmethod
    def utc(cls,v):
        if v.tzinfo is None:raise ValueError('Timezone required')
        return v.astimezone(timezone.utc)

    @field_validator('value')
    @classmethod
    def finite(cls,v):
        if v is not None and not math.isfinite(v):raise ValueError('Nonfinite measurement')
        return v


class Batch(BaseModel):
    model_config=ConfigDict(extra='forbid')
    events:list[Event]=Field(min_length=1,max_length=1000)


def summarize(events,now=None,registry=None,window_seconds=300,cadence_seconds=5):
    now=now or datetime.now(timezone.utc);registry=registry or {};seen={};groups={};duplicates=0;conflicts=0
    for e in sorted(events,key=lambda e:e.timestamp_utc):
        key=e.event_id or fingerprint([e.device_id,e.event_type,e.timestamp_utc.isoformat(),e.unit,e.data_mode])
        identity=(e.device_id,key)
        digest=fingerprint(e.model_dump(mode='json'))
        if identity in seen:
            duplicates+=1
            if seen[identity]!=digest:
                conflicts+=1
                for group_key,prior in groups.items():
                    if group_key[0]==e.device_id:prior['flags'].add('conflicting_duplicate')
            continue
        seen[identity]=digest
        age=(now-e.timestamp_utc).total_seconds()
        group=groups.setdefault((e.device_id,e.event_type,e.unit),{'values':[],'slots':set(),'flags':set(),'last':e.timestamp_utc,'events':[]})
        group['last']=max(group['last'],e.timestamp_utc)
        flags=[]
        if age< -30:flags.append('future_clock')
        if e.value is None:flags.append('missing_value')
        if e.quality not in ('pass','verified'):flags.append('quality_unverified')
        expected={'air_temperature':'°C','air_humidity':'%RH','raw_adc':'ADC'}
        if e.event_type not in expected or e.unit!=expected[e.event_type]:flags.append('unit_or_quantity_unverified')
        if e.event_type=='air_humidity' and e.value is not None and not 0<=e.value<=100:flags.append('humidity_out_of_range')
        if not e.calibration_id:flags.append('calibration_missing')
        group['flags'].update(flags)
        group['events'].append(e)
        if 0<=age<=window_seconds and e.value is not None and 'humidity_out_of_range' not in flags:
            group['values'].append(e.value);group['slots'].add(int(age//cadence_seconds))
    result=[]
    for (device,quantity,unit),g in groups.items():
        values=g['values'];deployment=registry.get(device,{})
        # Registry is trusted server-side evidence, never the client placement marker.
        field=bool(deployment.get('field_verified') and deployment.get('verified_by') and deployment.get('aoi_id')
                   and deployment.get('calibration_id') and deployment.get('applicable_K1'))
        field=field and all(e.data_mode=='observed' and e.delivery_mode!='replay' and e.calibration_id==deployment.get('calibration_id') for e in g['events'])
        stale=(now-g['last']).total_seconds()>30
        coverage=min(1,len(g['slots'])/(window_seconds//cadence_seconds+1))
        flags=sorted(g['flags']|({'stale'} if stale else set())|({'field_relevance_unverified'} if not field else set()))
        result.append({'device_id':device,'quantity':quantity,'unit':unit,'n':len(values),'mean':sum(values)/len(values) if values else None,
                       'min':min(values) if values else None,'max':max(values) if values else None,'last_observed_at':g['last'].isoformat(),
                       'window_seconds':window_seconds,'cadence_seconds':cadence_seconds,'coverage':coverage,'flags':flags,
                       'quality':'needs_review' if flags or coverage<.8 else 'pass','eligible_for_A1':bool(field and not flags and coverage>=.8),
                       'aoi_id':deployment.get('aoi_id') if field else None,
                       'evidence_class':'OBSERVED_FIELD' if field else 'SYNTHETIC' if all(e.data_mode=='simulated' for e in g['events']) else 'OBSERVED_BENCH',
                       'join_policy':'No crop evaluator consumer in V4.1; features are monitoring evidence only'})
    return {'schema_version':'h1-monitoring-1','features':result,'duplicates':duplicates,'conflicting_duplicates':conflicts,
            'policy':'300s window /5s slots /30s stale /80% coverage are engineering monitoring policies, not agronomic thresholds.'}


def ingest(batch,store):
    with LOCK:return _ingest_locked(batch,store)


def _ingest_locked(batch,store):
    store=Path(store);folder=store/'h1';folder.mkdir(parents=True,exist_ok=True)
    payload=batch.model_dump(mode='json');key=fingerprint(payload);path=folder/(key+'.json')
    duplicate=path.exists()
    if not duplicate:write_json(path,{'ingested_at':timestamp(),'batch':payload,'source_sha256':key})
    events=[]
    # Retain immutable history on disk; bounded newest 100 batches in monitoring view.
    for p in sorted(folder.glob('*.json'),key=lambda p:p.stat().st_mtime)[-100:]:
        events.extend(Batch.model_validate(json.loads(p.read_text(encoding='utf-8'))['batch']).events)
    result=summarize(events)
    result.update(batch_sha256=key,duplicate_batch=duplicate,registry_status='No verified deployment registry supplied; no automatic field join')
    write_json(store/'h1-latest.json',result)
    return result
