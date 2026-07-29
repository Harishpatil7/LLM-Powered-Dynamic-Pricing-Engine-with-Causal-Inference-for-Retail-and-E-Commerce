"""Tenant-aware entities for datasets, pricing analyses, and recommendations."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Retailer(Base):
    __tablename__ = "retailers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    datasets: Mapped[list["DatasetUpload"]] = relationship(back_populates="retailer", cascade="all, delete-orphan")
    products: Mapped[list["Product"]] = relationship(back_populates="retailer", cascade="all, delete-orphan")
    model_runs: Mapped[list["ModelRun"]] = relationship(back_populates="retailer", cascade="all, delete-orphan")
    memberships: Mapped[list["UserRetailer"]] = relationship(back_populates="retailer", cascade="all, delete-orphan")


class User(Base):
    """A local account. Hosted identity providers can replace this later."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    memberships: Mapped[list["UserRetailer"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserRetailer(Base):
    """Workspace membership keeps every retailer's data isolated by account."""

    __tablename__ = "user_retailers"
    __table_args__ = (UniqueConstraint("user_id", "retailer_id", name="uq_user_retailer"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    retailer_id: Mapped[str] = mapped_column(ForeignKey("retailers.id"), index=True)
    role: Mapped[str] = mapped_column(String(30), default="owner")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped["User"] = relationship(back_populates="memberships")
    retailer: Mapped["Retailer"] = relationship(back_populates="memberships")


class DatasetUpload(Base):
    __tablename__ = "dataset_uploads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    retailer_id: Mapped[str] = mapped_column(ForeignKey("retailers.id"), index=True)
    source_filename: Mapped[str] = mapped_column(String(500))
    storage_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    mapping: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    quality_report: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="validated", index=True)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    retailer: Mapped["Retailer"] = relationship(back_populates="datasets")
    observations: Mapped[list["SalesObservation"]] = relationship(back_populates="dataset", cascade="all, delete-orphan")
    model_runs: Mapped[list["ModelRun"]] = relationship(back_populates="dataset")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("retailer_id", "external_id", name="uq_product_retailer_external_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    retailer_id: Mapped[str] = mapped_column(ForeignKey("retailers.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    retailer: Mapped["Retailer"] = relationship(back_populates="products")
    observations: Mapped[list["SalesObservation"]] = relationship(back_populates="product")
    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="product")


class SalesObservation(Base):
    __tablename__ = "sales_observations"
    __table_args__ = (
        UniqueConstraint("dataset_id", "product_id", "observation_date", "store_id", "channel",
                         name="uq_observation_dataset_product_date_location"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("dataset_uploads.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    observation_date: Mapped[date] = mapped_column(Date, index=True)
    price: Mapped[float] = mapped_column(Float)
    units_sold: Mapped[float] = mapped_column(Float)
    unit_cost: Mapped[float] = mapped_column(Float)
    store_id: Mapped[str] = mapped_column(String(255), default="__default__")
    channel: Mapped[str] = mapped_column(String(255), default="__default__")
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    dataset: Mapped["DatasetUpload"] = relationship(back_populates="observations")
    product: Mapped["Product"] = relationship(back_populates="observations")


class ModelRun(Base):
    __tablename__ = "model_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    retailer_id: Mapped[str] = mapped_column(ForeignKey("retailers.id"), index=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("dataset_uploads.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    model_version: Mapped[str] = mapped_column(String(100))
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    diagnostics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    retailer: Mapped["Retailer"] = relationship(back_populates="model_runs")
    dataset: Mapped["DatasetUpload"] = relationship(back_populates="model_runs")
    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="model_run", cascade="all, delete-orphan")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    model_run_id: Mapped[str] = mapped_column(ForeignKey("model_runs.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    current_price: Mapped[float] = mapped_column(Float)
    recommended_price: Mapped[float] = mapped_column(Float)
    expected_demand: Mapped[float] = mapped_column(Float)
    expected_profit: Mapped[float] = mapped_column(Float)
    elasticity: Mapped[float] = mapped_column(Float)
    elasticity_ci_lower: Mapped[float | None] = mapped_column(Float, nullable=True)
    elasticity_ci_upper: Mapped[float | None] = mapped_column(Float, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    constraints_applied: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    model_run: Mapped["ModelRun"] = relationship(back_populates="recommendations")
    product: Mapped["Product"] = relationship(back_populates="recommendations")


class EvidenceDocument(Base):
    """Immutable, retrieved evidence used to ground a manager-facing report."""

    __tablename__ = "evidence_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    retailer_id: Mapped[str] = mapped_column(ForeignKey("retailers.id"), index=True)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(50), index=True)
    source_id: Mapped[str] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
