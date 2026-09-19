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


import re
from starlette.types import ASGIApp, Receive, Scope, Send


class NormalizePathMiddleware:
    """Normalize redundant slashes (e.g. //api/v1 -> /api/v1) before route resolution."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path", "")
            if "//" in path:
                clean_path = re.sub(r"/+", "/", path)
                scope = dict(scope)
                scope["path"] = clean_path
                if "raw_path" in scope:
                    scope["raw_path"] = clean_path.encode("latin-1")
        await self.app(scope, receive, send)


@asynccontextmanager
async def lifespan(_: FastAPI):
    import asyncio

    # Initialize database asynchronously in a background thread so uvicorn
    # binds to 0.0.0.0:$PORT immediately without triggering Render port-scan timeouts.
    asyncio.create_task(asyncio.to_thread(init_database))
    yield


app = FastAPI(
    title="LLM-DPECI API",
    version="0.1.0",
    docs_url=f"{settings.api_prefix}/docs",
    openapi_url=f"{settings.api_prefix}/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(NormalizePathMiddleware)

# The Vite development server is allowed during local development. Production
# origins will be configured explicitly before deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app|https://.*\.onrender\.com",
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


if __name__ == "__main__":
    import os
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port)

