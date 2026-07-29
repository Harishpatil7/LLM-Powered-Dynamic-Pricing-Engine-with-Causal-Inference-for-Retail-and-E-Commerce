from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.api.routes.datasets import router as datasets_router
from backend.api.routes.retailers import router as retailers_router
from backend.api.routes.causal import router as causal_router
from backend.api.routes.pricing import router as pricing_router
from backend.api.routes.products import router as products_router
from backend.api.routes.reports import router as reports_router
from backend.api.routes.auth import router as auth_router
from backend.database import init_database


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    yield


app = FastAPI(
    title="LLM-DPECI API",
    version="0.1.0",
    docs_url=f"{settings.api_prefix}/docs",
    openapi_url=f"{settings.api_prefix}/openapi.json",
    lifespan=lifespan,
)

# The Vite development server is allowed during local development. Production
# origins will be configured explicitly before deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(datasets_router, prefix=settings.api_prefix)
app.include_router(retailers_router, prefix=settings.api_prefix)
app.include_router(causal_router, prefix=settings.api_prefix)
app.include_router(pricing_router, prefix=settings.api_prefix)
app.include_router(products_router, prefix=settings.api_prefix)
app.include_router(reports_router, prefix=settings.api_prefix)
app.include_router(auth_router, prefix=settings.api_prefix)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Small dependency-free endpoint used to verify API/frontend connectivity."""

    return {"status": "ok", "environment": settings.environment}
