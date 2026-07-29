from datetime import datetime

from pydantic import BaseModel, Field


class ReportPreviewRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


class EvidenceSourceRead(BaseModel):
    id: str
    title: str
    source_type: str
    score: float
    created_at: datetime


class GroundedReportPreview(BaseModel):
    report_type: str
    answer: str
    sources: list[EvidenceSourceRead]
    warning: str | None = None


class GeminiReport(BaseModel):
    report_type: str
    answer: str
    sources: list[EvidenceSourceRead]
