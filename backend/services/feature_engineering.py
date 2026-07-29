"""Reproducible, data-backed feature engineering for pricing analyses."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.domain import Product, SalesObservation


MINIMUM_OBSERVATIONS = 30
MINIMUM_PRICE_VARIANTS = 2


@dataclass
class ProductPanel:
    product_id: str
    frame: pd.DataFrame
    confounders: list[str]
    eligible: bool
    limitations: list[str]


def build_product_panel(db: Session, product_id: str) -> ProductPanel:
    """Build one product's chronological panel from stored source observations.

    Calendar fields and lagged demand are derived mechanically from source dates
    and sales. Optional business context is used only when present in the CSV.
    """

    observations = list(db.scalars(
        select(SalesObservation)
        .where(SalesObservation.product_id == product_id)
        .order_by(SalesObservation.observation_date)
    ))
    if not observations:
        return ProductPanel(product_id, pd.DataFrame(), [], False, ["No observations found for this product."])

    rows = []
    for observation in observations:
        row = {
            "date": observation.observation_date,
            "price": observation.price,
            "units_sold": observation.units_sold,
            "unit_cost": observation.unit_cost,
            "store_id": observation.store_id,
            "channel": observation.channel,
            **(observation.context or {}),
        }
        rows.append(row)
    panel = pd.DataFrame(rows)
    panel["date"] = pd.to_datetime(panel["date"])
    panel = panel.sort_values("date").reset_index(drop=True)

    import numpy as np

    panel["day_of_week"] = panel["date"].dt.dayofweek
    panel["month"] = panel["date"].dt.month
    panel["day_of_year"] = panel["date"].dt.dayofyear
    panel["lagged_demand_1"] = panel["units_sold"].shift(1)
    panel["lagged_demand_7"] = panel["units_sold"].shift(7)

    # 1. Relative Price Index: ours vs. category median
    if "category" in panel.columns and not panel["category"].isna().all():
        cat_col = panel["category"].fillna("unknown")
        category_median = panel.groupby(cat_col)["price"].transform("median")
        panel["relative_price_index"] = panel["price"] / category_median
    else:
        panel["relative_price_index"] = panel["price"] / panel["price"].median()

    # 2. Competitor Price Ratio: our price vs competitor
    if "competitor_price" in panel.columns and not panel["competitor_price"].isna().all():
        comp_price = pd.to_numeric(panel["competitor_price"], errors="coerce").fillna(panel["price"])
        comp_price = comp_price.replace(0, 1.0)
        panel["competitor_price_ratio"] = panel["price"] / comp_price
    else:
        panel["competitor_price_ratio"] = 1.0

    # 3. Weather Severity Score (standardized)
    if "weather" in panel.columns and not panel["weather"].isna().all():
        weather_numeric = pd.to_numeric(panel["weather"], errors="coerce").fillna(0.0)
        mean_val = weather_numeric.mean()
        std_val = weather_numeric.std()
        if std_val > 0:
            panel["weather_severity"] = (weather_numeric - mean_val) / std_val
        else:
            panel["weather_severity"] = 0.0
    else:
        panel["weather_severity"] = 0.0

    # 4. Event Proximity: days to nearest event
    if "event" in panel.columns and not panel["event"].isna().all():
        has_event = panel["event"].notna() & panel["event"].ne(0) & panel["event"].ne("") & panel["event"].ne(False)
        event_dates = panel.loc[has_event, "date"]
        if not event_dates.empty:
            dates = panel["date"].to_numpy()
            ev_dates = event_dates.to_numpy()
            diffs = np.abs(dates[:, None] - ev_dates[None, :])
            diffs_days = diffs / np.timedelta64(1, "D")
            panel["event_proximity"] = np.min(diffs_days, axis=1)
        else:
            panel["event_proximity"] = 365.0
    else:
        panel["event_proximity"] = 365.0

    candidate_confounders = [
        "day_of_week", "month", "day_of_year", "lagged_demand_1", "lagged_demand_7",
        "relative_price_index", "competitor_price_ratio", "weather_severity", "event_proximity"
    ]
    for field in ("promotion", "inventory", "competitor_price", "event", "weather", "ad_spend", "customer_segment"):
        if field not in panel or panel[field].isna().all():
            continue
        if pd.api.types.is_numeric_dtype(panel[field]):
            candidate_confounders.append(field)
        else:
            encoded = pd.get_dummies(panel[field].astype("string"), prefix=field, dtype=float)
            panel = pd.concat([panel, encoded], axis=1)
            candidate_confounders.extend(encoded.columns.tolist())

    # Filter out columns with zero variance (constant values) to prevent collinearity issues
    candidate_confounders = [
        c for c in candidate_confounders
        if c in panel.columns and panel[c].nunique() > 1
    ]

    # Causal estimation must use a complete panel; the first seven rows have no
    # seven-day lag and are intentionally not imputed.
    modelling_panel = panel.dropna(subset=["price", "units_sold", *candidate_confounders]).copy()
    limitations: list[str] = []
    if len(modelling_panel) < MINIMUM_OBSERVATIONS:
        limitations.append(
            f"Only {len(modelling_panel)} complete observations are available; at least "
            f"{MINIMUM_OBSERVATIONS} are required."
        )
    if modelling_panel["price"].nunique() < MINIMUM_PRICE_VARIANTS:
        limitations.append("Price did not vary enough to estimate a price effect.")

    return ProductPanel(
        product_id=product_id,
        frame=modelling_panel,
        confounders=candidate_confounders,
        eligible=not limitations,
        limitations=limitations,
    )


def list_retailer_product_ids(db: Session, retailer_id: str) -> list[str]:
    return list(db.scalars(select(Product.id).where(Product.retailer_id == retailer_id)))
