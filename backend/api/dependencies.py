from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.domain import Retailer, User, UserRetailer
from backend.services.authentication import read_access_token


bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Session = Depends(get_db),
) -> User:
    user_id = read_access_token(credentials.credentials) if credentials else None
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to access this workspace.")
    return user


def get_authorized_retailer(db: Session, retailer_id: str, user: User) -> Retailer:
    retailer = db.get(Retailer, retailer_id)
    membership = db.scalar(select(UserRetailer).where(
        UserRetailer.user_id == user.id, UserRetailer.retailer_id == retailer_id,
    ))
    if retailer is None or membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
    return retailer
