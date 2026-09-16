"""Database initialization and connectivity verification script for MySQL or SQLite."""

from __future__ import annotations

import sys
from urllib.parse import urlparse

from sqlalchemy import inspect, text

from backend.config import settings
from backend.database import engine, init_database


def mask_url(url: str) -> str:
    """Mask password in database URL for safe logging."""
    try:
        parsed = urlparse(url)
        if parsed.password:
            netloc = parsed.netloc.replace(f":{parsed.password}@", ":******@")
            return parsed._replace(netloc=netloc).geturl()
    except Exception:
        pass
    return url


def main() -> None:
    db_url = settings.database_url
    masked = mask_url(db_url)
    print(f"[LLM-DPECI DB Init] Target Database: {masked}")
    print(f"[LLM-DPECI DB Init] Dialect: {engine.dialect.name}")

    try:
        # 1. Test raw connectivity
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            assert result.scalar() == 1
        print("[LLM-DPECI DB Init] Connectivity check: SUCCESS")

        # 2. Create tables
        print("[LLM-DPECI DB Init] Creating/verifying schema tables...")
        init_database()

        # 3. Inspect and display tables
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        print(f"[LLM-DPECI DB Init] Registered tables ({len(tables)}):")
        for table in sorted(tables):
            print(f"  - {table}")

        print("[LLM-DPECI DB Init] Database initialized successfully.")

    except Exception as exc:
        print(f"[LLM-DPECI DB Init] ERROR: Failed to connect or initialize database: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
