from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.dependencies import get_authorized_retailer, get_current_user
from backend.database import get_db
from backend.models.domain import ModelRun, Product, SalesObservation, User
from backend.schemas.causal import CausalRunRead, DiagnosticRead
from backend.services.causal_estimation import estimate_price_effect
from backend.services.evidence_retrieval import add_causal_evidence
from backend.services.feature_engineering import build_product_panel


router = APIRouter(prefix="/retailers/{retailer_id}/products", tags=["causal analysis"])


@router.post("/{product_id}/causal-runs", response_model=CausalRunRead, status_code=status.HTTP_201_CREATED)
def run_causal_analysis(
    retailer_id: str,
    product_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CausalRunRead:
    """Estimate the price-demand effect for a product using its uploaded history."""

    retailer = get_authorized_retailer(db, retailer_id, user)
    product = db.get(Product, product_id)
    if product is None or product.retailer_id != retailer.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Retailer or product not found.")

    panel = build_product_panel(db, product.id)
    # A model run is always recorded, even when the system blocks analysis.
    # This makes the reason visible to the business and preserves auditability.
    dataset_id = db.scalar(
        select(SalesObservation.dataset_id)
        .where(SalesObservation.product_id == product.id)
        .order_by(SalesObservation.id.desc())
    )
    if dataset_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Product has no uploaded observations.")

    if not panel.eligible:
        run = ModelRun(
            retailer_id=retailer.id,
            dataset_id=dataset_id,
            status="blocked",
            model_version="linear_dml_v1",
            configuration={"product_id": product.id, "confounders": panel.confounders},
            diagnostics={"limitations": panel.limitations},
        )
        db.add(run)
        db.flush()
        add_causal_evidence(db, product, run)
        db.commit()
        db.refresh(run)
        return CausalRunRead(
            model_run_id=run.id, status="blocked", product_id=product.id,
            observations=len(panel.frame), limitations=panel.limitations, created_at=run.created_at,
            causal_graph=None, identified_estimand=None,
        )

    result = estimate_price_effect(panel.frame, panel.confounders)
    diagnostics = [diagnostic.__dict__ for diagnostic in result.diagnostics]
    run = ModelRun(
        retailer_id=retailer.id,
        dataset_id=dataset_id,
        status="completed",
        model_version="linear_dml_v1",
        configuration={"product_id": product.id, "confounders": panel.confounders},
        diagnostics={
            "effect": result.effect,
            "ci_lower": result.ci_lower,
            "ci_upper": result.ci_upper,
            "observations": result.observations,
            "checks": diagnostics,
            "causal_graph": result.causal_graph,
            "identified_estimand": result.identified_estimand,
            "segment_elasticities": result.segment_elasticities,
        },
    )
    db.add(run)
    db.flush()
    add_causal_evidence(db, product, run)
    db.commit()
    db.refresh(run)
    return CausalRunRead(
        model_run_id=run.id, status="completed", product_id=product.id,
        observations=result.observations, effect=result.effect,
        ci_lower=result.ci_lower, ci_upper=result.ci_upper,
        diagnostics=[DiagnosticRead(**diagnostic) for diagnostic in diagnostics],
        causal_graph=result.causal_graph,
        identified_estimand=result.identified_estimand,
        segment_elasticities=result.segment_elasticities,
        created_at=run.created_at,
    )
