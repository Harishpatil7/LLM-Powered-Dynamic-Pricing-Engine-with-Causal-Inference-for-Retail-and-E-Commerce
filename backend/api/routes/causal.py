from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.dependencies import get_authorized_retailer, get_current_user
from backend.database import SessionLocal, get_db
from backend.models.domain import ModelRun, Product, SalesObservation, User
from backend.schemas.causal import CausalRunRead, DiagnosticRead
from backend.services.causal_estimation import estimate_price_effect
from backend.services.evidence_retrieval import add_causal_evidence
from backend.services.feature_engineering import build_product_panel


router = APIRouter(prefix="/retailers/{retailer_id}/products", tags=["causal analysis"])


def _to_causal_read(run: ModelRun, product_id: str) -> CausalRunRead:
    diagnostics_dict = run.diagnostics or {}
    checks = diagnostics_dict.get("checks", [])
    config = run.configuration or {}
    return CausalRunRead(
        model_run_id=run.id,
        status=run.status,  # type: ignore[arg-type]
        product_id=product_id,
        observations=diagnostics_dict.get("observations", 0),
        progress_step=config.get("progress_step"),
        effect=diagnostics_dict.get("effect"),
        ci_lower=diagnostics_dict.get("ci_lower"),
        ci_upper=diagnostics_dict.get("ci_upper"),
        diagnostics=[DiagnosticRead(**d) for d in checks if isinstance(d, dict)],
        limitations=diagnostics_dict.get("limitations", []),
        causal_graph=diagnostics_dict.get("causal_graph"),
        identified_estimand=diagnostics_dict.get("identified_estimand"),
        segment_elasticities=diagnostics_dict.get("segment_elasticities", {}),
        created_at=run.created_at,
    )


def _execute_causal_job(run_id: str, product_id: str, retailer_id: str) -> None:
    db = SessionLocal()
    try:
        run = db.get(ModelRun, run_id)
        product = db.get(Product, product_id)
        if not run or not product:
            return

        run.status = "running"
        run.configuration = {**(run.configuration or {}), "progress_step": "Building product feature panel"}
        db.commit()

        panel = build_product_panel(db, product.id)
        if not panel.eligible:
            run.status = "blocked"
            run.diagnostics = {"limitations": panel.limitations, "observations": len(panel.frame)}
            run.completed_at = datetime.now(timezone.utc)
            add_causal_evidence(db, product, run)
            db.commit()
            return

        run.configuration = {**(run.configuration or {}), "progress_step": "Estimating causal effect & refutations (DML)"}
        db.commit()

        result = estimate_price_effect(panel.frame, panel.confounders)
        diagnostics = [diagnostic.__dict__ for diagnostic in result.diagnostics]

        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.diagnostics = {
            "effect": result.effect,
            "ci_lower": result.ci_lower,
            "ci_upper": result.ci_upper,
            "observations": result.observations,
            "checks": diagnostics,
            "causal_graph": result.causal_graph,
            "identified_estimand": result.identified_estimand,
            "segment_elasticities": result.segment_elasticities,
        }
        run.configuration = {**(run.configuration or {}), "progress_step": "Complete"}
        add_causal_evidence(db, product, run)
        db.commit()

    except Exception as exc:
        run = db.get(ModelRun, run_id)
        if run:
            run.status = "failed"
            run.diagnostics = {"limitations": [f"Causal execution error: {exc}"]}
            db.commit()
    finally:
        db.close()


@router.post("/{product_id}/causal-runs", response_model=CausalRunRead, status_code=status.HTTP_201_CREATED)
def run_causal_analysis(
    retailer_id: str,
    product_id: str,
    background_tasks: BackgroundTasks,
    async_mode: bool = Query(False, description="Run model asynchronously in background"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CausalRunRead:
    """Estimate the price-demand effect for a product using its uploaded history."""

    retailer = get_authorized_retailer(db, retailer_id, user)
    product = db.get(Product, product_id)
    if product is None or product.retailer_id != retailer.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Retailer or product not found.")

    panel = build_product_panel(db, product.id)
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
            diagnostics={"limitations": panel.limitations, "observations": len(panel.frame)},
        )
        db.add(run)
        db.flush()
        add_causal_evidence(db, product, run)
        db.commit()
        db.refresh(run)
        return _to_causal_read(run, product.id)

    if async_mode:
        run = ModelRun(
            retailer_id=retailer.id,
            dataset_id=dataset_id,
            status="queued",
            model_version="linear_dml_v1",
            configuration={"product_id": product.id, "confounders": panel.confounders, "progress_step": "Queued in background"},
            diagnostics={"observations": len(panel.frame)},
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        background_tasks.add_task(_execute_causal_job, run.id, product.id, retailer.id)
        return _to_causal_read(run, product.id)

    # Synchronous execution
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
    return _to_causal_read(run, product.id)


@router.get("/{product_id}/causal-runs/latest", response_model=CausalRunRead)
def get_latest_causal_run(
    retailer_id: str,
    product_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CausalRunRead:
    retailer = get_authorized_retailer(db, retailer_id, user)
    product = db.get(Product, product_id)
    if product is None or product.retailer_id != retailer.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Retailer or product not found.")

    run = db.scalar(
        select(ModelRun)
        .where(ModelRun.retailer_id == retailer.id)
        .join(SalesObservation, SalesObservation.dataset_id == ModelRun.dataset_id)
        .where(SalesObservation.product_id == product.id)
        .order_by(ModelRun.created_at.desc())
    )
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No causal runs found for this product.")
    return _to_causal_read(run, product.id)


@router.get("/{product_id}/causal-runs/{model_run_id}", response_model=CausalRunRead)
def get_causal_run_by_id(
    retailer_id: str,
    product_id: str,
    model_run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CausalRunRead:
    retailer = get_authorized_retailer(db, retailer_id, user)
    product = db.get(Product, product_id)
    if product is None or product.retailer_id != retailer.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Retailer or product not found.")

    run = db.get(ModelRun, model_run_id)
    if not run or run.retailer_id != retailer.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model run not found.")
    return _to_causal_read(run, product.id)
