"""Persist validated retailer datasets without fabricating missing context."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import PROJECT_ROOT
from backend.models.domain import DatasetUpload, Product, Retailer, SalesObservation
from backend.schemas.datasets import DatasetColumnMapping
from backend.services.dataset_validation import OPTIONAL_FIELDS, ValidatedDataset, prepare_dataset_csv


from backend.services.storage import compute_sha256, get_storage_provider


def _json_value(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def persist_validated_dataset(
    *,
    db: Session,
    retailer: Retailer,
    content: bytes,
    filename: str,
    mapping: DatasetColumnMapping,
) -> DatasetUpload:
    """Validate, retain raw evidence, and create canonical product/observation rows.

    The caller owns the transaction. A failed validation writes no database rows.
    """

    prepared: ValidatedDataset = prepare_dataset_csv(content, filename, mapping)
    if prepared.report.status != "valid" or prepared.frame is None:
        raise ValueError("Only valid datasets can be persisted.")

    content_hash = compute_sha256(content)
    storage = get_storage_provider()

    dataset = DatasetUpload(
        retailer_id=retailer.id,
        source_filename=filename,
        file_hash=content_hash,
        mapping=mapping.model_dump(exclude_none=True),
        quality_report=prepared.report.model_dump(mode="json"),
        status="ingested",
        total_rows=prepared.report.total_rows,
        valid_rows=prepared.report.valid_rows,
    )
    db.add(dataset)
    db.flush()

    destination_rel = f"{retailer.id}/{dataset.id}.csv"
    saved_path = storage.save(content, destination_rel)
    dataset.storage_path = saved_path

    frame = prepared.frame
    products_by_external_id: dict[str, Product] = {}
    for external_id in frame["product_id"].drop_duplicates().tolist():
        product = db.scalar(select(Product).where(
            Product.retailer_id == retailer.id,
            Product.external_id == str(external_id),
        ))
        if product is None:
            product = Product(retailer_id=retailer.id, external_id=str(external_id))
            db.add(product)
            db.flush()
        products_by_external_id[str(external_id)] = product

    observations: list[SalesObservation] = []
    for row in frame.to_dict(orient="records"):
        context = {
            field: _json_value(row.get(field))
            for field in OPTIONAL_FIELDS
            if field in row and _json_value(row.get(field)) is not None
        }
        observations.append(SalesObservation(
            dataset_id=dataset.id,
            product_id=products_by_external_id[str(row["product_id"])].id,
            observation_date=row["date"].date(),
            price=float(row["price"]),
            units_sold=float(row["units_sold"]),
            unit_cost=float(row["unit_cost"]),
            store_id=str(row.get("store_id") or "__default__"),
            channel=str(row.get("channel") or "__default__"),
            context=context,
        ))
    db.add_all(observations)
    return dataset
