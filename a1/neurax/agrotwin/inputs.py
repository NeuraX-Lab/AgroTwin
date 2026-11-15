"""Bounded material inputs and WGS84 polygon validation."""
import hashlib
import json
import math
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def geometry_info(value):
    if value.get('type') != 'FeatureCollection' or len(value.get('features',[])) != 1:
        raise ValueError('One GeoJSON Polygon FeatureCollection is required')
    geo = value['features'][0].get('geometry',{})
    rings = geo.get('coordinates',[])
    if geo.get('type') != 'Polygon' or len(rings) != 1:
        raise ValueError('P0 supports one polygon without holes')
    ring = rings[0]
    if not 4 <= len(ring) <= 512:
        raise ValueError('Polygon needs 4..512 closed-ring positions')
    points = []
    for p in ring:
        if len(p) != 2 or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in p):
            raise ValueError('Finite [longitude, latitude] pairs required')
        lon,lat = map(float,p)
        if abs(lon)>180 or abs(lat)>85:
            raise ValueError('Coordinates outside supported WGS84 range')
        points.append([lon,lat])
    if points[0] != points[-1] or len({tuple(p) for p in points[:-1]}) != len(points)-1:
        raise ValueError('Close the ring and remove repeated vertices')
    def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def intersects(a,b,c,d):
        if max(a[0],b[0])<min(c[0],d[0]) or max(c[0],d[0])<min(a[0],b[0]):return False
        if max(a[1],b[1])<min(c[1],d[1]) or max(c[1],d[1])<min(a[1],b[1]):return False
        return cross(a,b,c)*cross(a,b,d)<=0 and cross(c,d,a)*cross(c,d,b)<=0
    for i in range(len(points)-1):
        for j in range(i+2,len(points)-1):
            if i==0 and j==len(points)-2:continue
            if intersects(points[i],points[i+1],points[j],points[j+1]):raise ValueError('Self-intersecting polygon')
    if max(p[0] for p in points)-min(p[0] for p in points)>5:
        raise ValueError('P0 does not support antimeridian/large polygons')
    # Spherical geodesic area, not a cadastral survey.
    area=abs(sum(math.radians(b[0]-a[0])*(math.sin(math.radians(a[1]))+math.sin(math.radians(b[1])))
                 for a,b in zip(points,points[1:])))*6371008.8**2/2
    if not 1 <= area <= 100_000_000:
        raise ValueError('P0 analysis area must be 1 m²..10,000 ha (operational limit)')
    canonical={'type':'Polygon','coordinates':[points]}
    return {'geometry_hash':fingerprint(canonical),'area_ha':round(area/10000,6),
            'centroid':[sum(p[k] for p in points[:-1])/(len(points)-1) for k in (0,1)],
            'scope':'research_polygon_not_surveyed_field','area_method':'spherical_geodesic_approximation'}


class FarmInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    previous_crop: str|None=Field(default=None,max_length=80)
    current_crop: str|None=Field(default=None,max_length=80)
    season: str|None=Field(default=None,max_length=80)
    irrigation_access: Literal['available','limited','unavailable']|None=None
    drainage_condition: Literal['good','poor','unknown']|None=None
    waterlogging_history: str|None=Field(default=None,max_length=200)
    management_plan: str|None=Field(default=None,max_length=300)
    goal: Literal['water','soil','income','explore']='explore'

    @field_validator('*',mode='before')
    @classmethod
    def missing(cls,value):
        if isinstance(value,str) and (not value.strip() or value.strip()=='unknown'):return None
        return value.strip() if isinstance(value,str) else value


class Period(BaseModel):
    model_config=ConfigDict(extra='forbid')
    start:date
    end:date

    @model_validator(mode='after')
    def calendar(self):
        if self.start.day!=1 or self.end.day!=1 or not 0<(self.end-self.start).days<=1830:
            raise ValueError('Use month starts and an exclusive end within five years')
        if not 1981<=self.start.year<=2030 or self.end.year>2031:raise ValueError('Period outside supported API bounds')
        return self


class AnalysisInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    aoi_id:str=Field(min_length=1,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    geometry:dict
    period:Period
    farm:FarmInput=Field(default_factory=FarmInput)
    source_mode:Literal['prefer_cache','live','offline']='prefer_cache'

    @field_validator('geometry')
    @classmethod
    def polygon(cls,value):geometry_info(value);return value
