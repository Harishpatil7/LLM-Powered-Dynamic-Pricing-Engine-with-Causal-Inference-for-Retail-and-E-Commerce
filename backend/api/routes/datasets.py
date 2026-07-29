import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.dependencies import get_authorized_retailer, get_current_user
from backend.database import get_db
from backend.models.domain import DatasetUpload, User
from backend.schemas.datasets import DatasetColumnMapping, DatasetQualityReport, DatasetUploadRead
from backend.services.dataset_ingestion import persist_validated_dataset
from backend.services.evidence_retrieval import add_dataset_evidence
from backend.services.dataset_validation import validate_dataset_csv


router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("/retailers/{retailer_id}", response_model=list[DatasetUploadRead])
def list_datasets(
    retailer_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[DatasetUploadRead]:
    """Return a retailer's uploaded datasets, newest first."""
    get_authorized_retailer(db, retailer_id, user)
    datasets = db.scalars(
        select(DatasetUpload)
        .where(DatasetUpload.retailer_id == retailer_id)
        .order_by(DatasetUpload.created_at.desc())
    )
    return [DatasetUploadRead.model_validate(item, from_attributes=True) for item in datasets]


@router.post("/validate", response_model=DatasetQualityReport)
async def validate_dataset(
    file: UploadFile = File(..., description="Retailer historical-sales CSV."),
    mapping_json: str = Form("{}", description="Optional JSON mapping of canonical fields to CSV columns."),
    _: User = Depends(get_current_user),
) -> DatasetQualityReport:
    """Validate a CSV before accepting it into the platform.

    Example mapping: {"date":"order_date","product_id":"sku","price":"unit_price"}
    """

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            detail="Upload a .csv file.")
    try:
        mapping = DatasetColumnMapping.model_validate(json.loads(mapping_json))
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"mapping_json must be a JSON object: {exc}") from exc

    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="The uploaded CSV is empty.")
    if len(content) > 100 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="CSV exceeds the 100 MB upload limit.")
    return validate_dataset_csv(content, file.filename, mapping)


@router.post("/retailers/{retailer_id}", response_model=DatasetUploadRead, status_code=status.HTTP_201_CREATED)
async def upload_dataset(
    retailer_id: str,
    file: UploadFile = File(..., description="Retailer historical-sales CSV."),
    mapping_json: str = Form("{}", description="Optional JSON mapping of canonical fields to CSV columns."),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DatasetUploadRead:
    """Store a valid CSV and its canonical observations for one retailer."""

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            detail="Upload a .csv file.")
    try:
        mapping = DatasetColumnMapping.model_validate(json.loads(mapping_json))
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"mapping_json must be a JSON object: {exc}") from exc
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="The uploaded CSV is empty.")
    if len(content) > 100 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="CSV exceeds the 100 MB upload limit.")

    retailer = get_authorized_retailer(db, retailer_id, user)
    try:
        dataset = persist_validated_dataset(
            db=db, retailer=retailer, content=content, filename=file.filename, mapping=mapping,
        )
        add_dataset_evidence(db, dataset)
        db.commit()
    except ValueError:
        db.rollback()
        report = validate_dataset_csv(content, file.filename, mapping)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=report.model_dump(mode="json"))
    except Exception:
        db.rollback()
        raise
    db.refresh(dataset)
    return DatasetUploadRead.model_validate(dataset, from_attributes=True)
