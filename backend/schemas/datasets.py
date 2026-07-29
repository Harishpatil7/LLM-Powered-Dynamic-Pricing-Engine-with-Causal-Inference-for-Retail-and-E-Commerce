from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DatasetColumnMapping(BaseModel):
    """Optional mapping from canonical names to column names in an uploaded CSV."""

    date: str | None = None
    product_id: str | None = None
    price: str | None = None
    units_sold: str | None = None
    unit_cost: str | None = None
    store_id: str | None = None
    channel: str | None = None
    category: str | None = None
    promotion: str | None = None
    inventory: str | None = None
    competitor_price: str | None = None
    event: str | None = None
    weather: str | None = None
    ad_spend: str | None = None
    customer_segment: str | None = None


class ColumnIssue(BaseModel):
    field: str
    severity: Literal["error", "warning"]
    message: str


class DatasetQualityReport(BaseModel):
    status: Literal["valid", "invalid"]
    source_filename: str
    total_rows: int
    valid_rows: int
    product_count: int
    date_start: str | None
    date_end: str | None
    eligible_product_count: int = Field(
        description="Products with at least 30 valid observations and two distinct prices."
    )
    resolved_columns: dict[str, str]
    issues: list[ColumnIssue]


class DatasetUploadRead(BaseModel):
    id: str
    retailer_id: str
    source_filename: str
    status: str
    total_rows: int
    valid_rows: int
    created_at: datetime
