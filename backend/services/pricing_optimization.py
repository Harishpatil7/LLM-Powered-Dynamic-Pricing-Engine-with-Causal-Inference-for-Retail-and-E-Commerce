"""Constrained Gaussian-process optimisation over a causal demand response."""

from __future__ import annotations

from dataclasses import dataclass

from skopt import gp_minimize
from skopt.space import Real


@dataclass
class OptimizationResult:
    optimal_price: float
    expected_demand: float
    expected_profit: float
    current_profit: float
    lower_bound: float
    upper_bound: float
    evaluations: int


def optimize_price(
    *,
    current_price: float,
    current_demand: float,
    unit_cost: float,
    causal_effect: float,
    minimum_margin: float,
    maximum_price_increase: float,
    maximum_price_decrease: float,
    evaluation_budget: int,
    competitor_price: float | None = None,
    max_competitor_undercut_pct: float | None = 0.10,
) -> OptimizationResult:
    """Maximise expected profit subject to explicit margin, price change, and competitor constraints.

    Demand is anchored to the most recent observed demand and adjusted by the
    causal DML effect. The GP optimiser searches only inside safe price bounds.
    """

    if unit_cost <= 0:
        raise ValueError("A positive unit cost is required for profit optimisation.")
    if current_price <= 0:
        raise ValueError("Current price must be positive.")
    if current_demand < 0:
        raise ValueError("Current demand cannot be negative.")

    margin_floor = unit_cost / (1 - minimum_margin)
    lower_bound = max(margin_floor, current_price * (1 - maximum_price_decrease))
    
    # Competitor proximity constraint: do not undercut competitor by more than max_competitor_undercut_pct
    if competitor_price is not None and competitor_price > 0:
        undercut_factor = 1.0 - (max_competitor_undercut_pct if max_competitor_undercut_pct is not None else 0.10)
        competitor_floor = competitor_price * undercut_factor
        lower_bound = max(lower_bound, competitor_floor)

    upper_bound = current_price * (1 + maximum_price_increase)
    if lower_bound >= upper_bound:
        # Prevent contradiction by capping lower_bound just below upper_bound
        lower_bound = max(margin_floor, upper_bound - 0.01)
    if lower_bound >= upper_bound:
        raise ValueError("Constraints leave no valid candidate price range.")

    def expected_demand(price: float) -> float:
        return max(0.0, current_demand + causal_effect * (price - current_price))

    def profit(price: float) -> float:
        return (price - unit_cost) * expected_demand(price)

    result = gp_minimize(
        func=lambda values: -profit(values[0]),
        dimensions=[Real(lower_bound, upper_bound, name="price")],
        n_calls=evaluation_budget,
        n_initial_points=min(5, evaluation_budget - 1),
        random_state=42,
    )
    optimal_price = float(result.x[0])
    return OptimizationResult(
        optimal_price=optimal_price,
        expected_demand=expected_demand(optimal_price),
        expected_profit=profit(optimal_price),
        current_profit=profit(current_price),
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        evaluations=evaluation_budget,
    )
