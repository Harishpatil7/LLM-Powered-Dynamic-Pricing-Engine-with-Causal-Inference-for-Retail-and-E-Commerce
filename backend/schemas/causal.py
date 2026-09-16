from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class DiagnosticRead(BaseModel):
    name: str
    passed: bool
    value: float
    message: str


class CausalRunRead(BaseModel):
    model_run_id: str
    status: Literal["queued", "running", "completed", "blocked", "failed"]
    product_id: str
    observations: int
    progress_step: str | None = None
    effect: float | None = None
    ci_lower: float | None = None
    ci_upper: float | None = None
    diagnostics: list[DiagnosticRead] = []
    limitations: list[str] = []
    causal_graph: dict | None = None
    identified_estimand: str | None = None
    segment_elasticities: dict[str, float] = {}
    created_at: datetime
