from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.dependencies import get_authorized_retailer, get_current_user
from backend.database import get_db
from backend.models.domain import Product, User
from backend.schemas.reports import EvidenceSourceRead, GeminiReport, GroundedReportPreview, ReportPreviewRequest
from backend.config import settings
from backend.services.evidence_retrieval import build_grounded_preview, retrieve_evidence
from backend.services.gemini_report import generate_gemini_report


router = APIRouter(prefix="/retailers/{retailer_id}/products", tags=["reports"])


@router.post("/{product_id}/reports/preview", response_model=GroundedReportPreview)
def preview_report(retailer_id: str, product_id: str, payload: ReportPreviewRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> GroundedReportPreview:
    retailer = get_authorized_retailer(db, retailer_id, user)
    product = db.get(Product, product_id)
    if product is None or product.retailer_id != retailer.id:
        raise HTTPException(status_code=404, detail="Retailer or product not found.")
    evidence = retrieve_evidence(db, retailer_id=retailer.id, product_id=product.id, question=payload.question)
    if not evidence:
        raise HTTPException(status_code=409, detail="No verified evidence exists for this product yet.")
    answer, warning = build_grounded_preview(evidence)
    return GroundedReportPreview(
        report_type="grounded_preview_no_llm",
        answer=answer,
        warning=warning,
        sources=[EvidenceSourceRead(
            id=item.document.id,
            title=item.document.title,
            source_type=item.document.source_type,
            score=item.score,
            created_at=item.document.created_at,
        ) for item in evidence],
    )


import hashlib
from fastapi import status
from backend.services.cache_service import (
    check_rate_limit,
    generate_cache_key,
    get_cached_json,
    set_cached_json,
)


@router.post("/{product_id}/reports/generate", response_model=GeminiReport)
def generate_report(
    retailer_id: str,
    product_id: str,
    payload: ReportPreviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GeminiReport:
    retailer = get_authorized_retailer(db, retailer_id, user)
    product = db.get(Product, product_id)
    if product is None or product.retailer_id != retailer.id:
        raise HTTPException(status_code=404, detail="Retailer or product not found.")

    # 1. Rate Limiting Protection (Token Bucket via Redis)
    is_allowed, remaining, reset_time = check_rate_limit(
        client_identifier=user.id,
        endpoint_name="generate_report",
        max_requests=20,
        window_seconds=60,
    )
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Please wait {reset_time} seconds before generating another report.",
            headers={"Retry-After": str(reset_time)},
        )

    # 2. Cache-Aside Lookup (In-Memory Redis Cache)
    question_hash = hashlib.sha256(payload.question.strip().lower().encode("utf-8")).hexdigest()[:16]
    cache_key = generate_cache_key("report", retailer.id, product.id, question_hash)
    cached_payload = get_cached_json(cache_key)
    if cached_payload:
        return GeminiReport(**cached_payload)

    # 3. Retrieve verified evidence documents
    evidence = retrieve_evidence(db, retailer_id=retailer.id, product_id=product.id, question=payload.question)
    if not evidence:
        raise HTTPException(
            status_code=409,
            detail="No verified evidence exists for this product yet. Please run causal analysis first.",
        )

    # 4. Generate report with Gemini or deterministic fallback
    report_type = "gemini_grounded_report"
    try:
        answer = generate_gemini_report(payload.question, evidence)
    except Exception as exc:
        preview_answer, preview_warning = build_grounded_preview(evidence)
        fallback_notice = (
            f"[Notice: Live Gemini generation unavailable ({exc}). Displaying verified deterministic evidence below.]\n\n"
        )
        answer = f"{fallback_notice}{preview_answer}"
        if preview_warning:
            answer += f"\n\nLimitations: {preview_warning}"
        report_type = "deterministic_audit_fallback"

    response = GeminiReport(
        report_type=report_type,
        answer=answer,
        sources=[
            EvidenceSourceRead(
                id=item.document.id,
                title=item.document.title,
                source_type=item.document.source_type,
                score=item.score,
                created_at=item.document.created_at,
            )
            for item in evidence
        ],
    )

    # 5. Populate Cache on successful AI generation
    if report_type == "gemini_grounded_report":
        try:
            set_cached_json(cache_key, response.model_dump(mode="json"), ttl_seconds=settings.redis_cache_ttl_seconds)
        except Exception:
            pass

    return response

