from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AuthCredentials(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=128)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    created_at: datetime


class AuthSession(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead
