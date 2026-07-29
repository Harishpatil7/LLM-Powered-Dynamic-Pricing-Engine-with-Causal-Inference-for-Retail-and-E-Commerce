from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RetailerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200, examples=["Acme Retail"])


class RetailerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    created_at: datetime
