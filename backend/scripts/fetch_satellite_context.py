"""Bounded public satellite downloads for review. No training or feature approval.

Keep original HTTP bytes in a cache with URL/time/hash; crop Sentinel COGs without
downloading global tiles. SMAP is explicitly L4 via NASA POWER, not L3 retrievals.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import requests
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/satellite-context-2026-11-14'
OUT = ROOT / 'runs/satellite-context-2026-11-14'
CONFIG = json.loads((ROOT/'config/resource-eda.json').read_text(encoding='utf-8-sig'))
AOI = dict(CONFIG['aoi'], label='Mỹ Thành, Đồng Tháp',
           alias_in_bich_workbook='Thạnh Mỹ, Tháp Mười',
           alias_status='user_declared_same_locality_2026-11-14_not_independently_geocoded',
           coordinate_anchor='previous_research_pack_retained_by_user_confirmation')
LAT, LON = AOI['latitude'], AOI['longitude']

def now(): return datetime.now(timezone.utc).isoformat()
def save(path, obj):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False,default=str),encoding='utf-8')
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class PublicCache:
    """Immutable URL-addressed public response cache; never reads credentials."""
    def __init__(self, directory):
        self.path=Path(directory).resolve(); self.path.mkdir(parents=True,exist_ok=True)
        self.ledger=self.path/'_requests.json'
        self.records=json.loads(self.ledger.read_text(encoding='utf-8')) if self.ledger.exists() else []
    def get(self,url,params=None):
        prepared=requests.Request('GET',url,params=params).prepare().url
        key=hashlib.sha256(prepared.encode()).hexdigest()
        p=self.path/'http'/key
        found=[r for r in self.records if r.get('url')==prepared and r.get('sha256')]
        if p.exists() and found:
            if sha(p)!=found[-1]['sha256']: raise ValueError('HTTP cache hash mismatch')
            return p.read_bytes()
        rec={'url':prepared,'requested_at_utc':now()}
        try:
            response=requests.get(prepared,timeout=(15,90),headers={'User-Agent':'NeuraX-public-EDA/1.0'})
            rec.update(status=response.status_code,final_url=response.url,retrieved_at_utc=now(),content_type=response.headers.get('content-type'))
            response.raise_for_status()
            p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(response.content)
            rec.update(local_path=str(p.relative_to(ROOT)),sha256=sha(p),bytes=p.stat().st_size)
            return response.content
        except Exception as exc:
            rec['error']=str(exc);raise
        finally:
            self.records.append(rec);save(self.ledger,self.records)
    def json(self,url,params=None): return json.loads(self.get(url,params))

def modis():
    d=RAW/'modis'; c=PublicCache(d); base='https://modis.ornl.gov/rst/api/v1/MOD13Q1'
    bands=c.json(base+'/bands');save(d/'bands.json',bands)
    dates=c.json(base+'/dates',{'latitude':LAT,'longitude':LON})
    save(d/'dates.json',dates)
    wanted=[v for v in dates['dates'] if '2023-01-01'<=v['calendar_date']<='2025-12-31']
    paths=[]
    for n in range(0,len(wanted),5):
        batch=wanted[n:n+5]
        j=c.json(base+'/subset',{'latitude':LAT,'longitude':LON,'startDate':batch[0]['modis_date'],
            'endDate':batch[-1]['modis_date'],'kmAboveBelow':2,'kmLeftRight':2})
        p=d/f'subset-{n//5:03d}.json';save(p,j);paths.append(str(p.relative_to(ROOT)))
        print('MODIS',n+len(batch),'/',len(wanted),j.get('nrows'),j.get('ncols'),flush=True)
    save(d/'manifest.json',{'source':'NASA ORNL TESViS MOD13Q1','aoi':AOI,'period':['2023-01-01','2025-12-31'],
        'expected_composites':len(wanted),'subset_files':paths,'requested_half_extent_km':2,
        'scientific_values_downloaded':True,'product_version_note':'Record native source filenames; do not infer subset processing version from current CMR catalogue.',
        'role':'regional_vegetation_context','dataset_selected':False,'features_selected':[]})

def smap():
    import xarray as xr
    import zarr
    from collections.abc import MutableMapping
    d=RAW/'smap-l4';c=PublicCache(d)
    base='https://nasa-power-smap.s3.amazonaws.com/smap/temporal/power_smap_daily_temporal_utc.zarr'
    metadata=c.json(base+'/.zmetadata');save(d/'source-zmetadata.json',metadata)
    class HTTPStore(MutableMapping):
        def __getitem__(self,key):
            try:return c.get(base+'/'+key)
            except requests.HTTPError as exc:
                if exc.response.status_code==404:raise KeyError(key) from exc
                raise
        def __setitem__(self,key,value):raise TypeError('read only public store')
        def __delitem__(self,key):raise TypeError('read only public store')
        def __iter__(self):return iter(metadata['metadata'])
        def __len__(self):return len(metadata['metadata'])
    ds=xr.open_zarr(HTTPStore(),consolidated=True,chunks=None)
    iy=int(np.argmin(abs(ds.lat.values-LAT)));ix=int(np.argmin(abs(ds.lon.values-LON)))
    # 7x7 regional cells around the native cell centre; preserve source coordinates.
    sub=ds[['SFMC','RZMC']].isel(lat=slice(iy-3,iy+4),lon=slice(ix-3,ix+4)).sel(time=slice('2015-03-31','2025-12-31')).load()
    sub.attrs.update(aoi_label=AOI['label'],interpretation='SMAP L4 model-assimilated estimates redistributed by POWER, not L3 retrievals or field measurements',
                     data_as_of_utc=now(),metadata_time_axis_warning='Source preallocates dates through 2029; extraction deliberately stops at 2025-12-31. Coverage must use non-fill values, not metadata end date.')
    sub.to_netcdf(d/'regional-daily.nc',engine='scipy')
    centre=sub.isel(lat=3,lon=3).to_dataframe()[['SFMC','RZMC']]
    centre.to_csv(d/'centroid-daily.csv',index_label='date')
    save(d/'manifest.json',{'source':'NASA POWER public SMAP L4 Zarr','source_url':base,'source_metadata_sha256':sha(d/'source-zmetadata.json'),
        'aoi':AOI,'source_attrs':dict(ds.attrs),'variable_attrs':{v:dict(ds[v].attrs) for v in ['SFMC','RZMC']},
        'native_centre':{'latitude':float(ds.lat.values[iy]),'longitude':float(ds.lon.values[ix])},
        'requested_period':['2015-03-31','2025-12-31'],'native_subset_shape':dict(sub.sizes),
        'scientific_values_downloaded':bool((np.isfinite(sub.SFMC.values)&(sub.SFMC.values>=0)&(sub.SFMC.values<=.9)).any()),
        'files':[{'path':str((d/n).relative_to(ROOT)),'sha256':sha(d/n)} for n in ['regional-daily.nc','centroid-daily.csv']],
        'version_notes':'POWER v10 metadata identifies processing_level 4; underlying upstream SMAP L4 version not pinned by this redistribution metadata. Source variables are marked status=reviewing.',
        'lineage_caution':'Model assimilates satellite observations and meteorological forcing; not independent validation of POWER weather or field moisture.',
        'dataset_selected':False,'features_selected':[]})
    print('SMAP',dict(sub.sizes),'finite centre',centre.notna().sum().to_dict(),flush=True)

def sentinel():
    import rasterio
    import fsspec
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds, Window
    d=RAW/'sentinel2';c=PublicCache(d)
    old=d/'manifest.json'
    if old.exists() and not (d/'legacy-collection-audit.json').exists():
        prior=json.loads(old.read_text(encoding='utf-8'))
        if prior.get('collection')!='sentinel-2-c1-l2a':
            save(d/'legacy-collection-audit.json',{'manifest':prior,'scenes':json.loads((d/'scenes.json').read_text(encoding='utf-8')),
                 'status':'quarantined_offset_metadata_inconsistent_in_two_2025_02_scenes',
                 'issue_reference':'https://github.com/Element84/earth-search/issues/71',
                 'action':'Use unharmonized C1 assets with explicit asset scale/offset. Preserve legacy data for audit; no heuristic offset correction.'})
    bbox=[LON-.012,LAT-.012,LON+.012,LAT+.012]
    j=c.json('https://earth-search.aws.element84.com/v1/search',{'collections':'sentinel-2-c1-l2a',
        'bbox':','.join(map(str,bbox)),'datetime':'2025-01-01T00:00:00Z/2025-12-31T23:59:59Z','limit':100})
    save(d/'stac-search.json',j)
    # Some STAC servers emit a next link even on a short final page.
    # Follow it and stop on an empty page; retain all catalogue response bytes.
    candidates=list(j['features']);page=j;page_number=1
    while page.get('features') and any(v.get('rel')=='next' for v in page.get('links',[])):
        if page_number>=5:raise ValueError('STAC pagination exceeded bounded 5 pages')
        link=next(v for v in page['links'] if v.get('rel')=='next')
        if link.get('method','GET')!='GET':raise ValueError('Unsupported STAC next method')
        page=c.json(link['href']);page_number+=1;save(d/f'stac-search-page-{page_number}.json',page)
        candidates.extend(page.get('features',[]))
    candidates=list({v['id']:v for v in candidates}.values());chosen=[]
    for months in [(1,2,3),(4,5,6),(7,8,9),(10,11,12)]:
        subset=[v for v in candidates if int(v['properties']['datetime'][5:7]) in months]
        chosen+=sorted(subset,key=lambda v:v['properties'].get('eo:cloud_cover',100))[:2]
    records=[]
    # Python HTTPS opener avoids Windows GDAL/SChannel credential-handle errors.
    # Certificate verification remains enabled. Objects are public, no AWS keys.
    fs=fsspec.filesystem('https',client_kwargs={'trust_env':True})
    for item in chosen:
        sid=item['id'];folder=d/sid;folder.mkdir(parents=True,exist_ok=True);save(folder/'stac-item.json',item)
        scene={'id':sid,'collection':'sentinel-2-c1-l2a','datetime':item['properties']['datetime'],'tile_cloud_cover_percent':item['properties'].get('eo:cloud_cover'),
            'boa_offset_applied':item['properties'].get('earthsearch:boa_offset_applied'),'assets':{}}
        for name in ['blue','green','red','nir','scl']:
            asset=item['assets'][name];url=asset['href'];p=folder/f'{name}.tif'
            if not p.exists():
                with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR',CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif',GDAL_HTTP_TIMEOUT='60'):
                    with rasterio.open(url,opener=fs.open) as src:
                        bounds=transform_bounds('EPSG:4326',src.crs,*bbox)
                        w=from_bounds(*bounds,src.transform)
                        # Expand to native integer pixel edges; never resample reflectance.
                        col0,row0=int(np.floor(w.col_off)),int(np.floor(w.row_off))
                        col1,row1=int(np.ceil(w.col_off+w.width)),int(np.ceil(w.row_off+w.height))
                        win=Window(col0,row0,col1-col0,row1-row0)
                        values=src.read(window=win)
                        profile=src.profile.copy();profile.update(height=values.shape[1],width=values.shape[2],transform=src.window_transform(win),driver='GTiff',compress='deflate')
                        with rasterio.open(p,'w',**profile) as dst:
                            dst.write(values);dst.update_tags(source_url=url,source_scene=sid,selection='native_window_no_reflectance_resampling')
            with rasterio.open(p) as src:
                scene['assets'][name]={'source_url':url,'source_metadata':asset,'path':str(p.relative_to(ROOT)),
                    'sha256':sha(p),'bytes':p.stat().st_size,'crs':str(src.crs),'resolution':list(src.res),'shape':[src.height,src.width],
                    'retrieved_at_utc':datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat(),'download_method':'anonymous HTTPS COG range window via fsspec opener; TLS verified; original asset metadata retained'}
            print('SENTINEL',sid,name,flush=True)
        records.append(scene)
        save(d/'scenes.json',records)
    save(d/'manifest.json',{'source':'ESA Copernicus Sentinel-2 L2A via Element84 Earth Search / AWS Sentinel COGs',
        'agency':'ESA / European Union Copernicus, not NASA','collection':'sentinel-2-c1-l2a','aoi':AOI,'bbox_wgs84':bbox,'period':['2025-01-01','2025-12-31'],
        'selection':'two lowest tile-cloud scenes per quarter; exploratory stratified sample, not complete phenology series',
        'catalogue_scene_count':len(candidates),'downloaded_scene_count':len(records),
        'reflectance_offset_note':'C1 unharmonized assets: apply asset raster:bands scale and offset exactly once. Legacy collection has reported inconsistent boa_offset_applied flags; preserved separately for audit.',
        'qa_note':'SCL has native 20m support; categorical nearest alignment does not create 10m QA information.',
        'license_url':'https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice',
        'scientific_values_downloaded':bool(records),'dataset_selected':False,'features_selected':[]})

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',choices=['modis','smap','sentinel'],required=True)
    args=p.parse_args();RAW.mkdir(parents=True,exist_ok=True);save(RAW/'aoi.json',AOI)
    {'modis':modis,'smap':smap,'sentinel':sentinel}[args.source]()
