from typing import Literal
from datetime import date,datetime,timezone,timedelta
from pydantic import BaseModel,Field,ConfigDict,model_validator
class Farm(BaseModel):
 model_config=ConfigDict(extra='forbid')
 current_crop:Literal['rice','baby_corn','mungbean','other','unknown']='unknown'
 goal:Literal['explore','water','soil','yield']='explore'
 irrigation:Literal['available','limited','none','unknown']='unknown'
 drainage:Literal['good','poor','unknown']='unknown'
 crop_interests:list[Literal['rice','baby_corn','mungbean']]=Field(default_factory=list,max_length=3)
 soil_ph:float|None=Field(default=None,ge=0,le=14)
 ph_method:Literal['H2O','KCl']|None=None
 soil_measured_at:date|None=None
 saline:bool|None=None
 acid_sulfate:bool|None=None
 window_start:date|None=None
 window_end:date|None=None
 conflicts:list[str]=Field(default_factory=list,max_length=10)
 @model_validator(mode='after')
 def dates(self):
  if self.window_start and self.window_end and self.window_end<=self.window_start:raise ValueError('Ngày kết thúc phải sau ngày bắt đầu')
  if self.soil_measured_at and self.soil_measured_at>datetime.now(timezone(timedelta(hours=7))).date():raise ValueError('Ngày đo không thể nằm trong tương lai')
  return self
class Analysis(BaseModel):
 model_config=ConfigDict(extra='forbid')
 region_id:Literal['MT-BLOCK-01']='MT-BLOCK-01'
 farm:Farm=Field(default_factory=Farm)
 question:str|None=Field(default=None,min_length=1,max_length=800)
