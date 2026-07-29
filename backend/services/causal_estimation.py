"""Double Machine Learning estimation and transparent diagnostic checks using DoWhy + EconML."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from dowhy import CausalModel
from sklearn.ensemble import RandomForestRegressor


@dataclass
class DiagnosticResult:
    name: str
    passed: bool
    value: float
    message: str


@dataclass
class CausalEstimate:
    effect: float
    ci_lower: float
    ci_upper: float
    observations: int
    diagnostics: list[DiagnosticResult]
    causal_graph: dict
    identified_estimand: str
    segment_elasticities: dict[str, float]


def estimate_price_effect(panel: pd.DataFrame, confounders: list[str], seed: int = 42) -> CausalEstimate:
    """Estimate the causal change in units sold for a one-unit price increase.

    This uses a DoWhy causal graph and identification steps, followed by EconML's
    Double Machine Learning (LinearDML) for estimation with segment-specific heterogeneous
    uplifts, and DoWhy refutation checks.
    """

    if len(panel) < 30:
        raise ValueError("At least 30 complete observations are required for DML estimation.")
    if panel["price"].nunique() < 2:
        raise ValueError("Price must vary to estimate a causal price effect.")

    # 1. Detect effect modifiers from the confounder set
    # Categories, promotions, store IDs, channels, and customer segments are treatment effect modifiers
    em_candidates = ["promotion", "store_id", "channel", "category", "customer_segment"]
    effect_modifiers = []
    for c in confounders:
        if any(c == cand or c.startswith(cand + "_") for cand in em_candidates):
            effect_modifiers.append(c)

    # 2. Initialize DoWhy causal model
    # We exclude relative_price_index and competitor_price_ratio from common causes
    # because they are direct mathematical transformations of the treatment (price)
    # and controlling for them causes perfect collinearity/multicollinearity.
    common_causes = [
        c for c in confounders 
        if c not in effect_modifiers 
        and c not in ("relative_price_index", "competitor_price_ratio")
    ]

    model = CausalModel(
        data=panel,
        treatment="price",
        outcome="units_sold",
        common_causes=common_causes,
        effect_modifiers=effect_modifiers
    )

    # 3. Identify the causal effect
    identified_estimand = model.identify_effect(proceed_when_unidentifiable=True)

    # 4. Estimate using EconML LinearDML through DoWhy
    model_y = RandomForestRegressor(n_estimators=100, min_samples_leaf=3, random_state=seed, n_jobs=-1)
    model_t = RandomForestRegressor(n_estimators=100, min_samples_leaf=3, random_state=seed + 1, n_jobs=-1)

    method_params = {
        "init_params": {
            "model_y": model_y,
            "model_t": model_t,
            "discrete_treatment": False,
            "cv": 3,
            "random_state": seed
        },
        "fit_params": {}
    }

    estimate = model.estimate_effect(
        identified_estimand,
        method_name="backdoor.econml.dml.LinearDML",
        method_params=method_params
    )

    # Get underlying EconML estimator
    econml_estimator = estimate.estimator.estimator

    effect = float(estimate.value)
    
    # Extract confidence intervals based on presence of effect modifiers X
    if effect_modifiers:
        X = panel[effect_modifiers].to_numpy(dtype=float)
        lower_arr, upper_arr = econml_estimator.ate_interval(X, T0=0, T1=1)
        lower = float(np.mean(lower_arr))
        upper = float(np.mean(upper_arr))
        
        # Calculate segment elasticities (uplift/heterogeneous effects)
        segment_effects = econml_estimator.const_marginal_effect(X).flatten()
        segment_elasticities = {}
        for idx, em_col in enumerate(effect_modifiers):
            unique_vals = panel[em_col].unique()
            if len(unique_vals) <= 10:
                for val in unique_vals:
                    mask = panel[em_col] == val
                    if mask.sum() >= 5:
                        seg_effects = segment_effects[mask]
                        segment_elasticities[f"{em_col}_{val}"] = float(np.mean(seg_effects))
    else:
        lower, upper = econml_estimator.ate_interval(T0=0, T1=1)
        lower = float(lower)
        upper = float(upper)
        segment_elasticities = {}

    # 5. Perform DoWhy refutations
    diagnostics: list[DiagnosticResult] = []

    # Placebo Treatment Refutation
    try:
        refute_placebo = model.refute_estimate(
            identified_estimand, estimate,
            method_name="placebo_treatment_refuter",
            placebo_type="permute",
            num_simulations=15
        )
        placebo_effect = float(refute_placebo.new_effect)
        placebo_passed = abs(placebo_effect) < abs(effect)
        diagnostics.append(DiagnosticResult(
            name="placebo_treatment",
            passed=placebo_passed,
            value=placebo_effect,
            message=(f"Placebo effect ({placebo_effect:.4f}) is smaller than the observed effect ({effect:.4f})." if placebo_passed
                     else f"Placebo effect ({placebo_effect:.4f}) was not smaller than the observed effect ({effect:.4f})."),
        ))
    except Exception as e:
        diagnostics.append(DiagnosticResult(
            name="placebo_treatment",
            passed=False,
            value=0.0,
            message=f"Placebo refutation failed: {e}",
        ))

    # Random Common Cause Refutation
    try:
        refute_random = model.refute_estimate(
            identified_estimand, estimate,
            method_name="random_common_cause",
            num_simulations=15
        )
        random_effect = float(refute_random.new_effect)
        relative_change = abs(relative_change := abs(random_effect - effect) / max(abs(effect), 1e-8))
        random_cause_passed = relative_change <= 0.60
        diagnostics.append(DiagnosticResult(
            name="random_common_cause",
            passed=random_cause_passed,
            value=relative_change,
            message=(f"Adding a random control kept the estimate within 60% (change: {relative_change * 100:.1f}%)." if random_cause_passed
                     else f"Adding a random control changed the estimate by {relative_change * 100:.1f}% (limit: 60%)."),
        ))
    except Exception as e:
        diagnostics.append(DiagnosticResult(
            name="random_common_cause",
            passed=False,
            value=0.0,
            message=f"Random common cause refutation failed: {e}",
        ))

    # Data Subset Refutation
    try:
        refute_subset = model.refute_estimate(
            identified_estimand, estimate,
            method_name="data_subset_refuter",
            subset_fraction=0.8,
            num_simulations=15
        )
        subset_effect = float(refute_subset.new_effect)
        subset_change = abs(subset_effect - effect) / max(abs(effect), 1e-8)
        subset_passed = subset_change <= 0.60
        diagnostics.append(DiagnosticResult(
            name="subset_stability",
            passed=subset_passed,
            value=subset_change,
            message=(f"An 80% subset kept the estimate within 60% (change: {subset_change * 100:.1f}%)." if subset_passed
                     else f"An 80% subset changed the estimate by {subset_change * 100:.1f}% (limit: 60%)."),
        ))
    except Exception as e:
        diagnostics.append(DiagnosticResult(
            name="subset_stability",
            passed=False,
            value=0.0,
            message=f"Subset stability refutation failed: {e}",
        ))

    # 6. Extract Graph JSON structure
    nodes = []
    for node in model._graph._graph.nodes:
        node_data = model._graph._graph.nodes[node]
        nodes.append({
            "id": str(node),
            "label": str(node),
            "observed": node_data.get("observed", "yes"),
            "penwidth": node_data.get("penwidth", 1)
        })
    edges = []
    for u, v in model._graph._graph.edges:
        edge_data = model._graph._graph.get_edge_data(u, v)
        edges.append({
            "source": str(u),
            "target": str(v),
            "penwidth": edge_data.get("penwidth", 1)
        })
    causal_graph = {"nodes": nodes, "edges": edges}

    # 7. Extract identified estimand description
    estimand_str = str(identified_estimand)

    return CausalEstimate(
        effect=effect,
        ci_lower=lower,
        ci_upper=upper,
        observations=len(panel),
        diagnostics=diagnostics,
        causal_graph=causal_graph,
        identified_estimand=estimand_str,
        segment_elasticities=segment_elasticities
    )
