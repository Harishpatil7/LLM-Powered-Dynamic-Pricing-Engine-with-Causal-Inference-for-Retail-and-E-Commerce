from backend.services.pricing_optimization import optimize_price


def test_optimizer_respects_margin_and_price_change_constraints() -> None:
    result = optimize_price(
        current_price=10.0,
        current_demand=30.0,
        unit_cost=6.0,
        causal_effect=-3.0,
        minimum_margin=0.20,
        maximum_price_increase=0.10,
        maximum_price_decrease=0.10,
        evaluation_budget=12,
    )

    assert 9.0 <= result.optimal_price <= 11.0
    assert result.optimal_price >= 7.5
    assert result.expected_profit >= result.current_profit


def test_optimizer_respects_competitor_proximity_constraint() -> None:
    result = optimize_price(
        current_price=10.0,
        current_demand=30.0,
        unit_cost=6.0,
        causal_effect=-3.0,
        minimum_margin=0.20,
        maximum_price_increase=0.20,
        maximum_price_decrease=0.20,
        evaluation_budget=12,
        competitor_price=12.0,
        max_competitor_undercut_pct=0.05,
    )
    assert result.optimal_price >= 11.40
