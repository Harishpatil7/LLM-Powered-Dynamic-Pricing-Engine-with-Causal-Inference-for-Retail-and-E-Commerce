"""Database entities registered with SQLAlchemy metadata."""

from backend.models.domain import DatasetUpload, EvidenceDocument, ModelRun, Product, Recommendation, Retailer, SalesObservation, User, UserRetailer

__all__ = [
    "DatasetUpload",
    "EvidenceDocument",
    "ModelRun",
    "Product",
    "Recommendation",
    "Retailer",
    "SalesObservation",
    "User",
    "UserRetailer",
]
