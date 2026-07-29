# LLM-DPECI

An evidence-grounded dynamic-pricing engine for authorised retail and e-commerce
data. Upload a daily product-sales CSV, estimate the causal price effect,
optimise a safe constrained price, and generate a Gemini explanation grounded in
the resulting evidence.

## Local setup

1. Create and activate a Python virtual environment. On this Windows project,
   use a short path because the repository path is long:
   `python -m venv C:\\tmp\\llm-dpeci-venv`
2. Install dependencies:
   `C:\\tmp\\llm-dpeci-venv\\Scripts\\python.exe -m pip install -r requirements.txt`
3. Copy `.env.example` to `.env`.
4. For Gemini reports, set `GEMINI_API_KEY` in `.env`. Set a unique
   `AUTH_SECRET_KEY` before deployment.
5. Start the API:
   `C:\\tmp\\llm-dpeci-venv\\Scripts\\python.exe -m uvicorn backend.main:app --reload`
6. In a second terminal, start the frontend:
   `cd frontend` then `npm.cmd run dev`

Visit `http://localhost:5173` to use the application. API documentation is at
`http://localhost:8000/api/v1/docs`.

## Demonstration flow

1. Create an account, then create a retailer workspace.
2. Select a CSV with `date`, `product_id`, `price`, `units_sold`, and `unit_cost`.
3. Validate it and review the quality report before storing it.
4. Select an uploaded product, run the causal analysis, and review every
   robustness diagnostic.
5. Optimise a price only if the screen reports it is safe; set the margin and
   allowed price-change guardrails first.
6. In **Evidence & Gemini Reports**, retrieve the verified sources, then create
   a grounded Gemini explanation if desired.

## Data policy

Only source data and derived calculations are used for pricing recommendations.
We do not generate fake weather, event, or causal-result values.

## Data ownership and traceability

Every upload belongs to a retailer workspace that is accessible only to the
signed-in account. The database links each processed observation, causal model
run, price recommendation, and report source to its retailer and source dataset.
This supports multi-business isolation and lets each report expose the exact
evidence it used.
