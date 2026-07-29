from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.api.dependencies import get_current_user
from backend.database import get_db
from backend.models.domain import User
from backend.schemas.auth import AuthCredentials, AuthSession, UserRead
from backend.services.authentication import create_access_token, hash_password, verify_password


router = APIRouter(prefix="/auth", tags=["authentication"])


def session_response(user: User) -> AuthSession:
    return AuthSession(access_token=create_access_token(user.id), user=UserRead.model_validate(user, from_attributes=True))


@router.post("/register", response_model=AuthSession, status_code=status.HTTP_201_CREATED)
def register(payload: AuthCredentials, db: Session = Depends(get_db)) -> AuthSession:
    user = User(email=str(payload.email).lower(), password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.") from exc
    db.refresh(user)
    return session_response(user)


@router.post("/login", response_model=AuthSession)
def login(payload: AuthCredentials, db: Session = Depends(get_db)) -> AuthSession:
    user = db.scalar(select(User).where(User.email == str(payload.email).lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email or password is incorrect.")
    return session_response(user)


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)) -> User:
    return user
