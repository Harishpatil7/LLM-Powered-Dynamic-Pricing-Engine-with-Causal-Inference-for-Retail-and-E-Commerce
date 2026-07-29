from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.api.dependencies import get_current_user
from backend.database import get_db
from backend.models.domain import Retailer, User, UserRetailer
from backend.schemas.retailers import RetailerCreate, RetailerRead


router = APIRouter(prefix="/retailers", tags=["retailers"])


@router.post("", response_model=RetailerRead, status_code=status.HTTP_201_CREATED)
def create_retailer(payload: RetailerCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Retailer:
    retailer = Retailer(name=payload.name.strip())
    db.add(retailer)
    db.flush()
    db.add(UserRetailer(user_id=user.id, retailer_id=retailer.id, role="owner"))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="A retailer with this name already exists.") from exc
    db.refresh(retailer)
    return retailer


@router.get("", response_model=list[RetailerRead])
def list_retailers(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[Retailer]:
    return list(db.scalars(
        select(Retailer).join(UserRetailer).where(UserRetailer.user_id == user.id).order_by(Retailer.name)
    ))
