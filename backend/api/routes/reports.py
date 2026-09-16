from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.dependencies import get_authorized_retailer, get_current_user
from backend.database import get_db
from backend.models.domain import Product, User
from backend.schemas.reports import EvidenceSourceRead, GeminiReport, GroundedReportPreview, ReportPreviewRequest
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


@router.post("/{product_id}/reports/generate", response_model=GeminiReport)
def generate_report(retailer_id: str, product_id: str, payload: ReportPreviewRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> GeminiReport:
    retailer = get_authorized_retailer(db, retailer_id, user)
    product = db.get(Product, product_id)
    if product is None or product.retailer_id != retailer.id:
        raise HTTPException(status_code=404, detail="Retailer or product not found.")
    evidence = retrieve_evidence(db, retailer_id=retailer.id, product_id=product.id, question=payload.question)
    if not evidence:
        raise HTTPException(status_code=409, detail="No verified evidence exists for this product yet. Please run causal analysis first.")
    
    report_type = "gemini_grounded_report"
    try:
        answer = generate_gemini_report(payload.question, evidence)
    except Exception as exc:
        preview_answer, preview_warning = build_grounded_preview(evidence)
        fallback_notice = f"[Notice: Live Gemini generation unavailable ({exc}). Displaying verified deterministic evidence below.]\n\n"
        answer = f"{fallback_notice}{preview_answer}"
        if preview_warning:
            answer += f"\n\nLimitations: {preview_warning}"
        report_type = "deterministic_audit_fallback"

    return GeminiReport(
        report_type=report_type,
        answer=answer,
        sources=[EvidenceSourceRead(
            id=item.document.id,
            title=item.document.title,
            source_type=item.document.source_type,
            score=item.score,
            created_at=item.document.created_at,
        ) for item in evidence],
    )
