"""Output contract for the selected V4 adapter, independent of V2 UI schemas."""
from typing import Any, Literal
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, model_validator
from research_runtime import Forecast


class Envelope(BaseModel):
    model_config = ConfigDict(extra='allow', allow_inf_nan=False)
    api_schema_version: Literal['fieldshift-dashboard-1'] = 'fieldshift-dashboard-1'
    selected_system: Literal['v4'] = 'v4'


class ModelSource(BaseModel):
    task: str
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class Inference(BaseModel):
    execution_mode: Literal['fresh_model_inference']
    model_version: Literal['v3-climatology-rag-v4-pooled']
    selection_id: str
    request_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    dataset_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    corpus_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    ml_selection_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    rag_selection_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    models: list[ModelSource] = Field(min_length=6, max_length=6)
    prediction_count: Literal[6]
    cached: Literal[False]


class AnalysisResponse(Envelope):
    schema_version: Literal['fieldshift-2']
    research_schema_version: Literal['fieldshift-research-1']
    run_id: str = Field(pattern=r'^v4-[a-f0-9]{32}$')
    region_id: Literal['MT-BLOCK-01']
    status: Literal['research_only']
    generated_at_utc: datetime
    domain_approved: Literal[False]
    input_origin: Literal['self_reported_unverified']
    forecasts: list[Forecast] = Field(min_length=6, max_length=6)
    decision: dict[str, Any]
    rag: dict[str, Any] | None
    question: str | None
    warnings: list[str]
    inference: Inference

    @model_validator(mode='after')
    def scientific_gates(self):
        if len({(f.target, f.horizon_months) for f in self.forecasts}) != 6:
            raise ValueError('Six unique forecast tasks required')
        options = self.decision.get('options', [])
        if {o['id'] for o in options} != {'R0', 'R1', 'R2'} or len(options) != 3:
            raise ValueError('Three reference rotations required')
        for option in options:
            if any(option.get(k) is not None for k in ['score', 'rank', 'probability_of_success']):
                raise ValueError('Agronomic scores are not approved')
            if option.get('domain_approved') is not False:
                raise ValueError('Domain approval is unavailable')
        if self.rag:
            abstains = self.rag['status'] == 'insufficient_evidence'
            if abstains and self.rag['citations']:
                raise ValueError('Abstention must not cite unsupported answers')
            if not abstains and (not self.rag['citations'] or not self.rag.get('source_bytes_verified')):
                raise ValueError('Answer requires verified source bytes')
        return self
