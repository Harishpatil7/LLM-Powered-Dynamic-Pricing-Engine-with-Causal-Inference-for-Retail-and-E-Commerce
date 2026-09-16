from datetime import datetime

from pydantic import BaseModel, Field


class PricingConstraints(BaseModel):
    minimum_margin: float = Field(default=0.15, ge=0, lt=1)
    maximum_price_increase: float = Field(default=0.20, gt=0, le=1)
    maximum_price_decrease: float = Field(default=0.20, gt=0, le=1)
    evaluation_budget: int = Field(default=20, ge=10, le=60)
    competitor_price: float | None = Field(default=None, ge=0)
    max_competitor_undercut_pct: float | None = Field(default=0.10, ge=0, le=1)


class RecommendationRead(BaseModel):
    id: str
    model_run_id: str
    product_id: str
    current_price: float
    recommended_price: float
    expected_demand: float
    expected_profit: float
    elasticity: float
    elasticity_ci_lower: float | None
    elasticity_ci_upper: float | None
    rationale: str | None
    constraints_applied: dict
    is_applied: bool = False
    applied_at: datetime | None = None
    created_at: datetime

