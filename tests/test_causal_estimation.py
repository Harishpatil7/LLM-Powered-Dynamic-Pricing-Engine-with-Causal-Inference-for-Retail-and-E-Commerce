import numpy as np
import pandas as pd

from backend.services.causal_estimation import estimate_price_effect


def test_double_ml_recovers_negative_price_effect_on_synthetic_ground_truth() -> None:
    """The test has a known causal process; production uses uploaded data instead."""
    rng = np.random.default_rng(7)
    observations = 180
    seasonality = rng.normal(size=observations)
    promotion = rng.integers(0, 2, size=observations)
    price = 10 + 0.8 * seasonality - 0.4 * promotion + rng.normal(scale=0.6, size=observations)
    units_sold = 80 - 3.0 * price + 4.0 * seasonality + 2.0 * promotion + rng.normal(scale=1.0, size=observations)
    panel = pd.DataFrame({
        "price": price,
        "units_sold": units_sold,
        "seasonality": seasonality,
        "promotion": promotion,
    })

    result = estimate_price_effect(panel, ["seasonality", "promotion"])

    assert result.effect < 0
    assert result.ci_lower < result.ci_upper
    assert len(result.diagnostics) == 3
