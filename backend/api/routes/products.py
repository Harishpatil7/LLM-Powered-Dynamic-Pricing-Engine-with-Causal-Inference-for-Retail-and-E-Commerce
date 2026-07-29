from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.dependencies import get_authorized_retailer, get_current_user
from backend.database import get_db
from backend.models.domain import Product, SalesObservation, User
from backend.schemas.products import ProductRead


router = APIRouter(prefix="/retailers/{retailer_id}/products", tags=["products"])


@router.get("", response_model=list[ProductRead])
def list_products(retailer_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[ProductRead]:
    get_authorized_retailer(db, retailer_id, user)
    products = list(db.scalars(
        select(Product).where(Product.retailer_id == retailer_id).order_by(Product.external_id)
    ))
    response: list[ProductRead] = []
    for product in products:
        latest = db.scalar(
            select(SalesObservation)
            .where(SalesObservation.product_id == product.id)
            .order_by(SalesObservation.observation_date.desc(), SalesObservation.id.desc())
        )
        response.append(ProductRead(
            id=product.id,
            retailer_id=product.retailer_id,
            external_id=product.external_id,
            name=product.name,
            category=product.category,
            latest_date=latest.observation_date if latest else None,
            latest_price=latest.price if latest else None,
            latest_demand=latest.units_sold if latest else None,
            latest_unit_cost=latest.unit_cost if latest else None,
        ))
    return response
