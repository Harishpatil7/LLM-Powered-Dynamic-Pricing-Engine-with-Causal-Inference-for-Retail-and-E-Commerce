import pandas as pd

from backend.services.m5_adapter import transform_m5_frames


def test_m5_adapter_creates_daily_price_demand_panel_without_inventing_cost() -> None:
    sales = pd.DataFrame([{
        "id": "ITEM_CA_1_validation", "item_id": "ITEM", "dept_id": "D1", "cat_id": "C1",
        "store_id": "CA_1", "state_id": "CA", "d_1": 2, "d_2": 3,
    }])
    calendar = pd.DataFrame([
        {"d": "d_1", "date": "2011-01-29", "wm_yr_wk": 11101, "event_name_1": None, "snap_CA": 0},
        {"d": "d_2", "date": "2011-01-30", "wm_yr_wk": 11101, "event_name_1": "Sporting", "snap_CA": 1},
    ])
    prices = pd.DataFrame([{"store_id": "CA_1", "item_id": "ITEM", "wm_yr_wk": 11101, "sell_price": 4.5}])

    adapted = transform_m5_frames(sales, calendar, prices)

    assert list(adapted.frame["units_sold"]) == [2, 3]
    assert list(adapted.frame["price"]) == [4.5, 4.5]
    assert "unit_cost" not in adapted.frame
    assert "cannot produce a factual profit recommendation" in adapted.limitations[0]
