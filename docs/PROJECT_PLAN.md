# LLM-DPECI Project Plan

## Product goal

Build a dynamic-pricing platform for retailers and e-commerce businesses. Each
business uploads its own authorised historical data. The system validates the
data, estimates a causal price-demand relationship, recommends a constrained
profit-maximising price, and shows the result in the existing frontend.

The Walmart M5 dataset is a **development and demonstration upload only**. It
does not become the source of recommendations for a retailer that uploads its
own data.

## Guiding rules

- No synthetic confounders, fabricated sales, or invented causal results.
- A recommendation must be traceable to a specific uploaded dataset and model
  run.
- The LLM explains verified results; it never chooses a price.
- A business with insufficient history receives an explicit "insufficient data"
  outcome, not a fake recommendation.
- The existing React frontend is preserved and connected incrementally.

## Target architecture

```text
Retailer CSV upload / authorised connector
                |
                v
Schema mapping, validation, and quality report
                |
                v
Tenant-isolated database + processed feature table
                |
                v
Causal demand model -> constrained price optimiser
                |
                v
Auditable recommendation + grounded explanation
                |
                v
FastAPI endpoints -> existing React frontend
```

## Data contract

The first release accepts CSV data with these required fields:

| Field | Meaning |
|---|---|
| `date` | Date of the observation |
| `product_id` | Product/SKU identifier |
| `price` | Price charged on that date |
| `units_sold` | Units sold on that date |
| `unit_cost` | Cost per unit |

Optional but valuable fields: `store_id`, `channel`, `category`, `promotion`,
`inventory`, `competitor_price`, `event`, `weather`, `ad_spend`, and
`customer_segment`.

The upload mapper will allow common business column names to be mapped to this
contract. The system will check types, missing values, negative values, price
variation, date coverage, and enough observations before allowing a causal run.

## Delivery phases

### Phase 1 — Foundation and data contract

1. Create the clean backend structure, environment configuration, and tests.
2. Define tenant, dataset, product, observation, model-run, and recommendation
   records.
3. Implement upload validation and a data-quality report.
4. Add an M5 adapter that converts M5 into the same generic data contract.

**Done when:** a CSV can be uploaded, validated, stored, and its quality report
is visible through the API.

### Phase 2 — Real data preparation

1. Aggregate uploaded observations to a product/store/day panel.
2. Create valid features from supplied data: date seasonality, lagged demand,
   promotions, events, inventory, and competitor context when available.
3. Store a reproducible processed-data version for every dataset upload.

**Done when:** every model run can identify the exact input dataset and feature
set that produced it.

### Phase 3 — Causal pricing model

1. Estimate price elasticity using Double Machine Learning.
2. Use only supplied and validated confounders.
3. Implement placebo-treatment, random-common-cause, and subset-stability
   checks where the data supports them.
4. Block recommendations when estimation diagnostics fail.

**Done when:** the API returns an elasticity estimate, uncertainty interval,
diagnostics, and clear limitations for an eligible product.

### Phase 4 — Constrained price optimisation

1. Convert the causal demand response into an expected-profit function.
2. Optimise price with minimum margin, minimum price, maximum price, and
maximum-change constraints.
3. Record the input assumptions and candidate evaluation results.

**Done when:** a valid model run produces an auditable price recommendation and
expected profit comparison with the current price.

### Phase 5 — Frontend integration

1. Connect dataset upload and data-quality screens.
2. Replace product and pricing-page dummy values with API data.
3. Connect dashboard KPIs, charts, model status, and recommendation details.
4. Keep unfinished features clearly marked rather than showing invented values.

**Done when:** a user can upload data, run a pricing analysis, and view the
real result in the existing UI.

### Phase 6 — Grounded reports and production readiness

1. Generate manager-facing reports from saved causal and optimisation results.
2. Optionally add an LLM with strict retrieval from those saved results.
3. Add authentication, tenant isolation, audit logging, test coverage,
documentation, and containerised deployment.

**Done when:** the platform is demonstrable end-to-end with real data and has
clear operational safeguards.

## Initial scope boundaries

The first working release accepts CSV uploads. Live integrations with Shopify,
WooCommerce, Amazon, POS systems, or competitor scraping are future connector
work. We will not claim real-time pricing until an authorised live data feed and
safe deployment controls exist.
