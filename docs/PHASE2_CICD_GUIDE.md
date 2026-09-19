# Phase 2: Continuous Integration & Continuous Delivery (CI/CD) Deep Dive

Welcome to Phase 2 of the SDE production hardening track. This guide covers how automated pipelines, quality gates, matrix testing, and GitHub Actions work in enterprise engineering environments.

---

## 1. What is CI/CD & Why Is It Crucial for Software Developers?

### Definitions
- **Continuous Integration (CI)**:
  - The practice where developers frequently merge code into the central branch.
  - Every merge triggers an **automated build and test pipeline**.
  - **The Goal**: Detect syntax errors, broken tests, and regressions in minutes rather than discovering them during deployment.
- **Continuous Delivery (CD)**:
  - Ensures that every passing build is automatically packaged (e.g., Docker image built and tagged) and ready for deployment to staging/production at the push of a button.
- **Continuous Deployment (CD)**:
  - Fully automated deployment: every change that passes all quality gates is automatically deployed to live production without manual human intervention.

---

## 2. GitHub Actions Pipeline Architecture

Our pipeline `.github/workflows/ci.yml` is structured into **4 parallel and gated jobs**:

```
                       ┌──────────────────────────────┐
                       │        Git Push / PR         │
                       └──────────────┬───────────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              ▼                       ▼                       ▼
   ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐
   │ 1. Backend Lint    │  │ 2. Backend Tests   │  │ 3. Frontend Build  │
   │   (Ruff / Flake8)  │  │   (Pytest Matrix)  │  │   (Node 20 / Vite) │
   └──────────┬─────────┘  └────────────────────┘  └──────────┬─────────┘
              │                                               │
              └───────────────────────┬───────────────────────┘
                                      ▼
                           ┌────────────────────┐
                           │  4. Docker Build   │
                           │   (Buildx Test)    │
                           └────────────────────┘
```

### Key Workflow Directives Explained

#### 1. Concurrency Management
```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```
- **The Problem**: If a developer pushes 3 rapid commits in 2 minutes, GitHub Actions would spin up 3 separate runner instances, wasting free runner quota (2,000 mins/month) and queueing jobs.
- **The Fix**: `cancel-in-progress: true` automatically kills older running builds for the same branch whenever a new commit arrives, ensuring only the latest code is tested.

#### 2. Dependency Caching
```yaml
- uses: actions/setup-python@v5
  with:
    python-version: "3.11"
    cache: "pip"
```
- Instead of re-downloading 300MB of Python wheels from PyPI on every test run, GitHub Actions caches the pip cache directory based on the hash of `requirements.txt`.
- **Result**: Cuts runner setup time from 90 seconds to under 5 seconds.

#### 3. Matrix Strategy
```yaml
strategy:
  fail-fast: false
  matrix:
    python-version: ["3.11"]
```
- In enterprise systems, you might support Python 3.11, 3.12, and 3.13.
- Defining a matrix instructs GitHub to spin up isolated virtual machines for each version in parallel.
- `fail-fast: false` ensures that if one Python version fails, the runner continues testing the other versions to provide full diagnostic telemetry.

#### 4. Job Dependencies (`needs:`)
```yaml
docker-validation:
  needs: [backend-lint, frontend-build]
```
- Building Docker images is resource-intensive (taking 2–4 minutes).
- By adding `needs: [backend-lint, frontend-build]`, Docker builds are only triggered **after** code linting and frontend compilation succeed. If linting fails with a syntax error, the Docker job never starts, saving resources.

---

## 3. Testing Principles for SDEs: The Testing Pyramid

In technical interviews, interviewers often ask: *"How do you design a comprehensive test suite?"*

```
                 / \
                /   \     E2E Tests (Playwright / Cypress)
               /     \    Few, slow, tests full browser flow
              /───────\
             /         \    Integration Tests
            /           \   FastAPI endpoints + In-Memory SQLite / Mock APIs
           /─────────────\
          /               \   Unit Tests (Pytest)
         /                 \  Fast, pure math/logic tests (EconML, RAG prompt)
        /───────────────────\
```

### Mocking External APIs in CI (Critical Rule)
- **Why CI Tests Must Never Call the Live Gemini API:**
  1. **Flakiness**: If Google's API has network latency or 503 hiccups, your build turns red even if your code is 100% bug-free.
  2. **Billing / Quota**: Running 50 PRs a day could exhaust your API rate limits or incur unnecessary cloud charges.
  3. **Security**: Secrets should not be exposed in untrusted pull requests from public forks.
- **Solution**: Mock the response from `client.models.generate_content()` in test fixtures so unit and integration tests run entirely offline in milliseconds.

---

## 4. SDE Placement Interview Flashcards (CI/CD & DevOps)

### Q1: *"What is the difference between Continuous Delivery and Continuous Deployment?"*
> **Answer:** *"In Continuous Delivery, every passing code commit is automatically built, tested, and packaged into a deployable artifact (e.g., a tagged Docker image), but deployment to production requires manual authorization. In Continuous Deployment, there is no manual intervention: every commit that passes the automated pipeline is automatically deployed directly to production."*

### Q2: *"How do you handle sensitive credentials (API keys, DB passwords) in CI/CD?"*
> **Answer:** *"Never commit secrets to git. In GitHub Actions, secrets are stored in encrypted repository settings (`Secrets and variables > Actions`) and injected as environment variables into runner steps at runtime using `${{ secrets.MY_SECRET }}`. The runner automatically redacts secret values from console log outputs."*

### Q3: *"What is a flaky test and how do you prevent it?"*
> **Answer:** *"A flaky test is a test that intermittently passes or fails without any changes to the underlying code. Common causes include reliance on external third-party APIs, race conditions in asynchronous code, hardcoded timestamps, or shared mutable state. We prevent flaky tests by mocking external network calls, using in-memory databases with isolated transactions per test, and avoiding non-deterministic time-based sleeps."*
