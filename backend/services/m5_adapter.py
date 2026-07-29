"""Adapter for the Walmart M5 dataset.

M5 is used only as a real-data demonstration source. It contains sales, prices,
and calendar context but no true unit cost, so outputs are eligible for causal
demand analysis only—not factual profit optimisation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass
class M5AdaptedPanel:
    frame: pd.DataFrame
    limitations: list[str]


def transform_m5_frames(
    sales: pd.DataFrame,
    calendar: pd.DataFrame,
    prices: pd.DataFrame,
) -> M5AdaptedPanel:
    """Turn selected M5 series from wide daily columns into a canonical panel."""

    day_columns = [column for column in sales.columns if column.startswith("d_")]
    required_sales = {"id", "item_id", "dept_id", "cat_id", "store_id", "state_id"}
    if not day_columns or not required_sales.issubset(sales.columns):
        raise ValueError("Sales data must contain M5 identifiers and one or more d_* daily columns.")
    if not {"d", "date", "wm_yr_wk"}.issubset(calendar.columns):
        raise ValueError("Calendar data must contain d, date, and wm_yr_wk.")
    if not {"store_id", "item_id", "wm_yr_wk", "sell_price"}.issubset(prices.columns):
        raise ValueError("Price data must contain store_id, item_id, wm_yr_wk, and sell_price.")

    panel = sales.melt(
        id_vars=["id", "item_id", "dept_id", "cat_id", "store_id", "state_id"],
        value_vars=day_columns,
        var_name="d",
        value_name="units_sold",
    )
    calendar_columns = [
        column for column in ("d", "date", "wm_yr_wk", "event_name_1", "event_type_1", "snap_CA", "snap_TX", "snap_WI")
        if column in calendar.columns
    ]
    panel = panel.merge(calendar[calendar_columns], on="d", how="left", validate="many_to_one")
    panel = panel.merge(
        prices[["store_id", "item_id", "wm_yr_wk", "sell_price"]],
        on=["store_id", "item_id", "wm_yr_wk"],
        how="left",
        validate="many_to_one",
    )
    panel = panel.dropna(subset=["date", "sell_price"]).copy()
    state_snap_column = {"CA": "snap_CA", "TX": "snap_TX", "WI": "snap_WI"}
    panel["snap_available"] = [
        row.get(state_snap_column.get(str(row["state_id"])[:2], ""), 0)
        for _, row in panel.iterrows()
    ]
    panel["event"] = panel.get("event_name_1", pd.Series(index=panel.index, dtype="string")).fillna("none")
    canonical = panel.rename(columns={"id": "product_id", "sell_price": "price"})[
        ["date", "product_id", "store_id", "price", "units_sold", "dept_id", "cat_id", "event", "snap_available"]
    ].sort_values(["product_id", "date"]).reset_index(drop=True)
    return M5AdaptedPanel(
        frame=canonical,
        limitations=[
            "M5 does not provide unit cost; this panel cannot produce a factual profit recommendation.",
            "M5 does not provide real competitor prices or local weather data.",
        ],
    )


def load_m5_series(data_dir: Path, series_ids: list[str]) -> M5AdaptedPanel:
    """Load selected M5 series without materialising every sales series in memory."""

    if not series_ids:
        raise ValueError("Provide at least one M5 series id; loading every M5 series is intentionally disabled.")
    data_dir = Path(data_dir)
    sales_path = data_dir / "sales_train_validation.csv"
    calendar_path = data_dir / "calendar.csv"
    prices_path = data_dir / "sell_prices.csv"
    missing = [path.name for path in (sales_path, calendar_path, prices_path) if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing M5 file(s): {', '.join(missing)}")

    selected_chunks = []
    for chunk in pd.read_csv(sales_path, chunksize=100):
        selected = chunk[chunk["id"].isin(series_ids)]
        if not selected.empty:
            selected_chunks.append(selected)
    if not selected_chunks:
        raise ValueError("None of the requested series ids exist in the M5 sales file.")
    sales = pd.concat(selected_chunks, ignore_index=True)
    pairs = sales[["store_id", "item_id"]].drop_duplicates()
    prices = pd.read_csv(prices_path)
    prices = prices.merge(pairs, on=["store_id", "item_id"], how="inner")
    return transform_m5_frames(sales, pd.read_csv(calendar_path), prices)
