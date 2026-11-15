"""Small shared, safe file utilities; no remote upload or code execution."""
from __future__ import annotations
import hashlib, json, os, tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

IGNORE_DIRS = {'.git','.venv','venv','env','node_modules','__pycache__','.mypy_cache','.pytest_cache','runs','.idea','dist','build'}

def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')

def write_json(path: Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.neurax-', suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(value,f,ensure_ascii=False,indent=2,default=str,allow_nan=False)
            f.write('\n')
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def sha256_file(path: Path, limit_bytes: int = 128*1024*1024) -> str | None:
    if path.stat().st_size > limit_bytes: return None
    digest = hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()

def file_kind(path:Path) -> str:
    ext=path.suffix.lower()
    return {
        '.csv':'table','.tsv':'table','.parquet':'table','.xlsx':'spreadsheet','.xlsm':'spreadsheet',
        '.xls':'spreadsheet','.json':'json','.jsonl':'jsonl','.geojson':'geojson','.gpkg':'vector',
        '.shp':'vector','.tif':'raster','.tiff':'raster','.nc':'array','.nc4':'array',
        '.h5':'array','.hdf5':'array','.hdf':'array','.db':'sqlite','.sqlite':'sqlite',
        '.sqlite3':'sqlite','.sql':'sql_text','.md':'document','.txt':'document','.pdf':'document',
        '.docx':'document','.pptx':'document','.yaml':'config','.yml':'config','.ipynb':'notebook',
        '.zip':'archive','.gz':'archive','.7z':'archive','.tar':'archive',
        '.png':'image','.jpg':'image','.jpeg':'image','.webp':'image','.xml':'document',
    }.get(ext,'unknown')
