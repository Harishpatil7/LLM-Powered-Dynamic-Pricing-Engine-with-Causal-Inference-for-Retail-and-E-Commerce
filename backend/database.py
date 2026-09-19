"""SQLAlchemy setup and database lifecycle helpers."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pymysql
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import PROJECT_ROOT, settings

# Enable pure-python PyMySQL driver as default MySQLdb drop-in
try:
    pymysql.install_as_MySQLdb()
except Exception:
    pass


def resolved_database_url(database_url: str) -> str:
    """Normalize database URL for production and local environments."""
    from sqlalchemy.engine import make_url

    # Automatically map generic mysql:// to pure-python mysql+pymysql://
    if database_url.startswith("mysql://"):
        database_url = "mysql+pymysql://" + database_url.removeprefix("mysql://")

    prefix = "sqlite:///./"
    if database_url.startswith(prefix):
        relative_path = database_url.removeprefix(prefix)
        return f"sqlite:///{(PROJECT_ROOT / relative_path).as_posix()}"

    if database_url.startswith("mysql"):
        try:
            url = make_url(database_url)
            system_dbs = {"", "/", "sys", "mysql", "information_schema", "performance_schema"}
            # TiDB Cloud and MySQL require a target user database ('test'). System schemas disallow user tables.
            if not url.database or url.database.strip().lower() in system_dbs:
                url = url.set(database="test")
                database_url = url.render_as_string(hide_password=False)
        except Exception:
            pass

    return database_url




def build_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite"):
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )

    # Production connection pool settings for MySQL / PostgreSQL
    return create_engine(
        database_url,
        pool_pre_ping=True,   # Validates connections before using them
        pool_recycle=3600,    # Recycles connections every hour to prevent MySQL stale socket timeouts
        pool_size=10,         # Base connection pool size
        max_overflow=20,      # Overflow connections allowed during traffic spikes
    )


class Base(DeclarativeBase):
    pass


DATABASE_URL = resolved_database_url(settings.database_url)
if DATABASE_URL.startswith("sqlite:///"):
    database_path = DATABASE_URL[len("sqlite:///"):]
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
else:
    try:
        from sqlalchemy.engine import make_url

        _u = make_url(DATABASE_URL)
        print(f"INFO: [Database] Connecting to {_u.drivername} at {_u.host}:{_u.port}/{_u.database} (user: {_u.username})")
    except Exception:
        pass

engine = build_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_missing_columns(target_engine: Engine) -> None:
    """Safely apply non-destructive schema updates for newly introduced columns."""
    from sqlalchemy import inspect, text

    inspector = inspect(target_engine)
    existing_tables = set(inspector.get_table_names())

    with target_engine.begin() as conn:
        if "dataset_uploads" in existing_tables:
            columns = {c["name"] for c in inspector.get_columns("dataset_uploads")}
            if "file_hash" not in columns:
                conn.execute(text("ALTER TABLE dataset_uploads ADD COLUMN file_hash VARCHAR(64)"))
            if "storage_path" not in columns:
                conn.execute(text("ALTER TABLE dataset_uploads ADD COLUMN storage_path VARCHAR(1000)"))

        if "recommendations" in existing_tables:
            columns = {c["name"] for c in inspector.get_columns("recommendations")}
            if "is_applied" not in columns:
                conn.execute(text("ALTER TABLE recommendations ADD COLUMN is_applied BOOLEAN DEFAULT 0"))
            if "applied_at" not in columns:
                conn.execute(text("ALTER TABLE recommendations ADD COLUMN applied_at DATETIME"))


def init_database() -> None:
    """Create the local development schema. Migrations replace this in production."""

    # Import models before metadata creation so all tables are registered.
    import backend.models  # noqa: F401

    try:
        Base.metadata.create_all(bind=engine)
        _migrate_missing_columns(engine)
        print("INFO: [Database] Database initialized and verified successfully.")
    except Exception as exc:
        err_msg = str(exc)
        if "1142" in err_msg or "denied to user" in err_msg:
            print("\n" + "=" * 80)
            print("⚠️ [DATABASE PERMISSION DENIED IN TIDB / MYSQL]")
            print(f"Details: {exc}")
            print("\n👉 HOW TO FIX IN TIDB CLOUD:")
            print("1. Log in to TiDB Cloud (https://tidbcloud.com)")
            print("2. Click your Cluster -> 'SQL Editor' in the left menu")
            print("3. Run the following command:")
            print("   GRANT ALL PRIVILEGES ON *.* TO '3ivhXSazAyWvNw8.root'@'%';")
            print("   GRANT ALL PRIVILEGES ON test.* TO '3ivhXSazAyWvNw8.root'@'%';")
            print("   FLUSH PRIVILEGES;")
            print("=" * 80 + "\n")
        else:
            print(f"WARNING: [Database] Database initialization encountered a temporary connection issue: {exc}")

