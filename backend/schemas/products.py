from datetime import date

from pydantic import BaseModel


class ProductRead(BaseModel):
    id: str
    retailer_id: str
    external_id: str
    name: str | None
    category: str | None
    latest_date: date | None = None
    latest_price: float | None = None
    latest_demand: float | None = None
    latest_unit_cost: float | None = None
