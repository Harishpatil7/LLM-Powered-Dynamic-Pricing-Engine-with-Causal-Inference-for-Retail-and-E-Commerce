"""Validation for retailer historical-sales CSV uploads.

The validator deliberately performs no data imputation or synthetic enrichment.
It reports what the uploaded data can support and prevents invalid source data
from entering later causal-modelling stages.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

import pandas as pd

from backend.schemas.datasets import ColumnIssue, DatasetColumnMapping, DatasetQualityReport


REQUIRED_FIELDS = ("date", "product_id", "price", "units_sold", "unit_cost")
OPTIONAL_FIELDS = (
    "store_id",
    "channel",
    "category",
    "promotion",
    "inventory",
    "competitor_price",
    "event",
    "weather",
    "ad_spend",
    "customer_segment",
)


@dataclass
class ValidatedDataset:
    """A quality report and canonical rows that are valid for storage."""

    report: DatasetQualityReport
    frame: pd.DataFrame | None

# These aliases let common exports work without a manual mapping. A user can
# still supply a mapping when their export uses a different column name.
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "date": ("date", "transaction_date", "order_date", "sales_date"),
    "product_id": ("product_id", "sku", "item_id", "product", "item"),
    "price": ("price", "unit_price", "selling_price", "sale_price"),
    "units_sold": ("units_sold", "quantity", "quantity_sold", "units", "sales_qty"),
    "unit_cost": ("unit_cost", "cost", "cost_price", "product_cost"),
    "store_id": ("store_id", "store", "location_id"),
    "channel": ("channel", "sales_channel"),
    "category": ("category", "product_category", "department"),
    "promotion": ("promotion", "is_promotion", "discount", "promo"),
    "inventory": ("inventory", "stock", "stock_on_hand"),
    "competitor_price": ("competitor_price", "market_price"),
    "event": ("event", "event_name", "holiday"),
    "weather": ("weather", "weather_score"),
    "ad_spend": ("ad_spend", "marketing_spend"),
    "customer_segment": ("customer_segment", "segment"),
}


def _normalise_column_name(name: str) -> str:
    return name.strip().casefold().replace(" ", "_").replace("-", "_")


def _resolve_columns(
    columns: list[str], mapping: DatasetColumnMapping
) -> tuple[dict[str, str], list[ColumnIssue]]:
    lookup = {_normalise_column_name(column): column for column in columns}
    resolved: dict[str, str] = {}
    issues: list[ColumnIssue] = []

    for field in (*REQUIRED_FIELDS, *OPTIONAL_FIELDS):
        explicit_name = getattr(mapping, field)
        if explicit_name:
            if explicit_name in columns:
                resolved[field] = explicit_name
            else:
                issues.append(ColumnIssue(
                    field=field,
                    severity="error" if field in REQUIRED_FIELDS else "warning",
                    message=f"Mapped column '{explicit_name}' was not found in the CSV.",
                ))
            continue

        for alias in COLUMN_ALIASES[field]:
            source_name = lookup.get(_normalise_column_name(alias))
            if source_name:
                resolved[field] = source_name
                break

    for field in REQUIRED_FIELDS:
        if field not in resolved and not any(issue.field == field for issue in issues):
            issues.append(ColumnIssue(
                field=field,
                severity="error",
                message=(f"Required field '{field}' was not found. Map one of your CSV columns "
                         f"to '{field}'."),
            ))

    return resolved, issues


def prepare_dataset_csv(
    content: bytes, filename: str, mapping: DatasetColumnMapping | None = None
) -> ValidatedDataset:
    """Read a CSV and return its report plus valid rows in canonical field names."""

    mapping = mapping or DatasetColumnMapping()
    try:
        frame = pd.read_csv(BytesIO(content))
    except (UnicodeDecodeError, pd.errors.ParserError) as exc:
        return ValidatedDataset(report=DatasetQualityReport(
            status="invalid", source_filename=filename, total_rows=0, valid_rows=0,
            product_count=0, date_start=None, date_end=None, eligible_product_count=0,
            resolved_columns={},
            issues=[ColumnIssue(field="file", severity="error", message=f"Unable to read CSV: {exc}")],
        ), frame=None)

    resolved, issues = _resolve_columns(list(frame.columns), mapping)
    if any(issue.severity == "error" for issue in issues):
        return ValidatedDataset(report=DatasetQualityReport(
            status="invalid", source_filename=filename, total_rows=len(frame), valid_rows=0,
            product_count=0, date_start=None, date_end=None, eligible_product_count=0,
            resolved_columns=resolved, issues=issues,
        ), frame=None)

    canonical = pd.DataFrame({field: frame[source] for field, source in resolved.items()})
    canonical["date"] = pd.to_datetime(canonical["date"], errors="coerce")
    for field in ("price", "units_sold", "unit_cost"):
        if field in canonical:
            canonical[field] = pd.to_numeric(canonical[field], errors="coerce")
    for field in ("competitor_price", "promotion", "inventory", "ad_spend", "weather"):
        if field in canonical:
            canonical[field] = pd.to_numeric(canonical[field], errors="coerce")
    canonical["product_id"] = canonical["product_id"].astype("string").str.strip()

    valid_mask = (
        canonical["date"].notna()
        & canonical["product_id"].notna()
        & canonical["product_id"].ne("")
        & canonical["price"].notna() & canonical["price"].gt(0)
        & canonical["units_sold"].notna() & canonical["units_sold"].ge(0)
        & canonical["unit_cost"].notna() & canonical["unit_cost"].ge(0)
    )
    valid = canonical.loc[valid_mask].copy()
    invalid_count = len(canonical) - len(valid)
    if invalid_count:
        issues.append(ColumnIssue(
            field="rows", severity="warning",
            message=(f"{invalid_count} row(s) have missing/invalid required values or negative "
                     "quantities/costs and cannot be used for modelling."),
        ))

    if valid.empty:
        issues.append(ColumnIssue(
            field="rows", severity="error",
            message="No valid rows remain after required-field validation.",
        ))
        return ValidatedDataset(report=DatasetQualityReport(
            status="invalid", source_filename=filename, total_rows=len(frame), valid_rows=0,
            product_count=0, date_start=None, date_end=None, eligible_product_count=0,
            resolved_columns=resolved, issues=issues,
        ), frame=None)

    group_sizes = valid.groupby("product_id").size()
    price_counts = valid.groupby("product_id")["price"].nunique()
    eligible_products = (group_sizes.ge(30) & price_counts.ge(2)).sum()
    if eligible_products == 0:
        issues.append(ColumnIssue(
            field="price", severity="warning",
            message=("No product has at least 30 observations and two different prices. "
                     "The upload is valid, but it is not yet eligible for causal price estimation."),
        ))

    return ValidatedDataset(report=DatasetQualityReport(
        status="valid", source_filename=filename, total_rows=len(frame), valid_rows=len(valid),
        product_count=int(valid["product_id"].nunique()),
        date_start=valid["date"].min().date().isoformat(),
        date_end=valid["date"].max().date().isoformat(),
        eligible_product_count=int(eligible_products), resolved_columns=resolved, issues=issues,
    ), frame=valid)


def validate_dataset_csv(
    content: bytes, filename: str, mapping: DatasetColumnMapping | None = None
) -> DatasetQualityReport:
    """Return a report without persisting the source CSV."""

    return prepare_dataset_csv(content, filename, mapping).report
