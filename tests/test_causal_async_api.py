from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from backend.main import app
from backend.api.dependencies import get_current_user
from backend.models.domain import DatasetUpload, Product, Retailer, SalesObservation, User, UserRetailer


def test_causal_async_endpoints_flow(monkeypatch):
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
    user = User(email="data_scientist@acme.com", password_hash="secret")
    retailer = Retailer(name="Acme Analytics")
    db.add_all([user, retailer])
    db.flush()

    membership = UserRetailer(user_id=user.id, retailer_id=retailer.id, role="owner")
    product = Product(retailer_id=retailer.id, external_id="SKU-ASYNC-1", name="Test SKU")
    dataset = DatasetUpload(retailer_id=retailer.id, source_filename="data.csv")
    db.add_all([membership, product, dataset])
    db.flush()

    # Add enough observations for panel building (MINIMUM_OBSERVATIONS = 30)
    from datetime import date, timedelta
    base_date = date(2025, 1, 1)
    obs = []
    for i in range(40):
        obs.append(SalesObservation(
            dataset_id=dataset.id,
            product_id=product.id,
            observation_date=base_date + timedelta(days=i),
            price=10.0 + (i % 3) * 0.5,
            units_sold=20.0 - (i % 3) * 2.0,
            unit_cost=5.0,
            store_id="S1",
            channel="online",
        ))
    db.add_all(obs)
    db.commit()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user
    monkeypatch.setattr("backend.api.routes.causal.SessionLocal", TestingSessionLocal)

    try:
        client = TestClient(app)

        # Trigger async causal run
        resp = client.post(f"/api/v1/retailers/{retailer.id}/products/{product.id}/causal-runs?async_mode=true")
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["status"] in ("queued", "running", "completed")
        model_run_id = data["model_run_id"]
        assert model_run_id is not None

        # Fetch status by model_run_id
        status_resp = client.get(f"/api/v1/retailers/{retailer.id}/products/{product.id}/causal-runs/{model_run_id}")
        assert status_resp.status_code == 200, status_resp.text
        status_data = status_resp.json()
        assert status_data["model_run_id"] == model_run_id

        # Fetch latest causal run
        latest_resp = client.get(f"/api/v1/retailers/{retailer.id}/products/{product.id}/causal-runs/latest")
        assert latest_resp.status_code == 200, latest_resp.text
        assert latest_resp.json()["model_run_id"] == model_run_id
    finally:
        app.dependency_overrides.clear()
