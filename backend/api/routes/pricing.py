from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.dependencies import get_authorized_retailer, get_current_user
from backend.database import get_db
from backend.models.domain import ModelRun, Product, Recommendation, SalesObservation, User
from backend.schemas.pricing import PricingConstraints, RecommendationRead
from backend.services.pricing_optimization import optimize_price
from backend.services.evidence_retrieval import add_recommendation_evidence


router = APIRouter(prefix="/retailers/{retailer_id}/products", tags=["pricing"])


@router.post("/{product_id}/model-runs/{model_run_id}/recommendations", response_model=RecommendationRead,
             status_code=status.HTTP_201_CREATED)
def create_recommendation(
    retailer_id: str,
    product_id: str,
    model_run_id: str,
    constraints: PricingConstraints,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Recommendation:
    """Optimise a price only when the specified causal run is trustworthy."""

    retailer = get_authorized_retailer(db, retailer_id, user)
    product = db.get(Product, product_id)
    run = db.get(ModelRun, model_run_id)
    if product is None or run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Retailer, product, or model run not found.")
    if product.retailer_id != retailer.id or run.retailer_id != retailer.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource does not belong to this retailer.")
    if run.status != "completed" or run.configuration.get("product_id") != product.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="This model run is not a completed analysis for the requested product.")

    diagnostics = run.diagnostics
    checks = diagnostics.get("checks", [])
    if not checks or not all(check.get("passed") for check in checks):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Causal diagnostics did not pass; price optimisation is blocked.")
    effect = float(diagnostics["effect"])
    ci_lower = float(diagnostics["ci_lower"])
    ci_upper = float(diagnostics["ci_upper"])
    if ci_upper >= 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="The causal price effect is not confidently negative; price optimisation is blocked.")

    latest = db.scalar(
        select(SalesObservation)
        .where(SalesObservation.product_id == product.id)
        .order_by(SalesObservation.observation_date.desc(), SalesObservation.id.desc())
    )
    if latest is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Product has no sales observations.")
    try:
        comp_price = constraints.competitor_price
        if comp_price is None and latest.context and "competitor_price" in latest.context:
            try:
                comp_price = float(latest.context["competitor_price"])
            except (ValueError, TypeError):
                pass

        result = optimize_price(
            current_price=latest.price,
            current_demand=latest.units_sold,
            unit_cost=latest.unit_cost,
            causal_effect=effect,
            minimum_margin=constraints.minimum_margin,
            maximum_price_increase=constraints.maximum_price_increase,
            maximum_price_decrease=constraints.maximum_price_decrease,
            evaluation_budget=constraints.evaluation_budget,
            competitor_price=comp_price,
            max_competitor_undercut_pct=constraints.max_competitor_undercut_pct,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    recommendation = Recommendation(
        model_run_id=run.id,
        product_id=product.id,
        current_price=latest.price,
        recommended_price=result.optimal_price,
        expected_demand=result.expected_demand,
        expected_profit=result.expected_profit,
        elasticity=effect,
        elasticity_ci_lower=ci_lower,
        elasticity_ci_upper=ci_upper,
        rationale=("Recommendation is constrained by minimum margin and allowed price change, "
                   "and is based on a causal DML demand response with passed diagnostics."),
        constraints_applied={
            **constraints.model_dump(),
            "lower_price_bound": result.lower_bound,
            "upper_price_bound": result.upper_bound,
            "current_expected_profit": result.current_profit,
            "evaluation_count": result.evaluations,
        },
    )
    db.add(recommendation)
    db.flush()
    add_recommendation_evidence(db, recommendation)
    db.commit()
    db.refresh(recommendation)
    return recommendation


@router.post("/{product_id}/recommendations/{recommendation_id}/apply", response_model=RecommendationRead)
def apply_recommendation(
    retailer_id: str,
    product_id: str,
    recommendation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Recommendation:
    """Commit the recommended price to production and record deployment audit evidence."""

    retailer = get_authorized_retailer(db, retailer_id, user)
    product = db.get(Product, product_id)
    recommendation = db.get(Recommendation, recommendation_id)

    if product is None or recommendation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product or recommendation not found.")
    if product.retailer_id != retailer.id or recommendation.product_id != product.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation does not match product or retailer.")

    from datetime import datetime, timezone
    from backend.models.domain import EvidenceDocument

    recommendation.is_applied = True
    recommendation.applied_at = datetime.now(timezone.utc)

    # Save deployment audit evidence
    db.add(EvidenceDocument(
        retailer_id=retailer.id,
        product_id=product.id,
        source_type="applied_price",
        source_id=recommendation.id,
        title=f"Price applied: {product.external_id}",
        content=(f"Recommendation {recommendation.id} applied to catalog on {recommendation.applied_at.isoformat()}. "
                 f"New deployed price: {recommendation.recommended_price:.2f} (previously {recommendation.current_price:.2f}). "
                 f"Expected profit: {recommendation.expected_profit:.2f}."),
        metadata_json={
            "applied_price": recommendation.recommended_price,
            "previous_price": recommendation.current_price,
            "applied_at": recommendation.applied_at.isoformat(),
        },
    ))

    db.commit()
    db.refresh(recommendation)
    return recommendation


@router.get("/{product_id}/recommendations/latest", response_model=RecommendationRead)
def get_latest_recommendation(
    retailer_id: str,
    product_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Recommendation:
    retailer = get_authorized_retailer(db, retailer_id, user)
    product = db.get(Product, product_id)
    if product is None or product.retailer_id != retailer.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Retailer or product not found.")

    rec = db.scalar(
        select(Recommendation)
        .where(Recommendation.product_id == product.id)
        .order_by(Recommendation.created_at.desc())
    )
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No recommendations found for this product.")
    return rec

