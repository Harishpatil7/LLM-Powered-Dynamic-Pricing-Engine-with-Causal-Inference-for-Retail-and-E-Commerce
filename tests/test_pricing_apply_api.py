from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from backend.main import app
from backend.api.dependencies import get_current_user
from backend.models.domain import DatasetUpload, EvidenceDocument, ModelRun, Product, Recommendation, Retailer, User, UserRetailer


def test_apply_recommendation_flow():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    db = TestingSessionLocal()
    user = User(email="pricing_manager@acme.com", password_hash="secret")
    retailer = Retailer(name="Acme Supermarket")
    db.add_all([user, retailer])
    db.flush()

    membership = UserRetailer(user_id=user.id, retailer_id=retailer.id, role="owner")
    product = Product(retailer_id=retailer.id, external_id="SKU-888", name="Organic Milk")
    dataset = DatasetUpload(retailer_id=retailer.id, source_filename="sample.csv")
    db.add_all([membership, product, dataset])
    db.flush()

    model_run = ModelRun(
        retailer_id=retailer.id,
        dataset_id=dataset.id,
        status="completed",
        model_version="linear_dml_v1",
        configuration={"product_id": product.id},
    )
    db.add(model_run)
    db.flush()

    rec = Recommendation(
        model_run_id=model_run.id,
        product_id=product.id,
        current_price=4.50,
        recommended_price=4.20,
        expected_demand=120.0,
        expected_profit=250.0,
        elasticity=-1.5,
    )
    db.add(rec)
    db.commit()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        client = TestClient(app)
        # Apply recommendation
        resp = client.post(f"/api/v1/retailers/{retailer.id}/products/{product.id}/recommendations/{rec.id}/apply")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["is_applied"] is True
        assert data["applied_at"] is not None
        assert data["recommended_price"] == 4.20

        # Verify evidence document created in db
        evidence = db.scalar(
            select(EvidenceDocument).where(
                EvidenceDocument.retailer_id == retailer.id,
                EvidenceDocument.source_type == "applied_price",
                EvidenceDocument.source_id == rec.id,
            )
        )
        assert evidence is not None
        assert "4.20" in evidence.content
    finally:
        app.dependency_overrides.clear()
