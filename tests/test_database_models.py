from datetime import date

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.domain import DatasetUpload, Product, Retailer, SalesObservation


def test_database_schema_and_tenant_product_identity(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    retailer = Retailer(name="Acme Retail")
    session.add(retailer)
    session.flush()
    dataset = DatasetUpload(retailer_id=retailer.id, source_filename="sales.csv")
    product = Product(retailer_id=retailer.id, external_id="SKU-1")
    session.add_all([dataset, product])
    session.flush()
    session.add(SalesObservation(
        dataset_id=dataset.id, product_id=product.id, observation_date=date(2025, 1, 1),
        price=10.0, units_sold=3.0, unit_cost=4.0,
    ))
    session.commit()

    table_names = set(inspect(engine).get_table_names())
    assert {"retailers", "dataset_uploads", "products", "sales_observations", "model_runs", "recommendations"} <= table_names
    assert product.retailer_id == retailer.id


def test_mysql_engine_configuration() -> None:
    from backend.database import build_engine
    mysql_url = "mysql+pymysql://testuser:testpass@localhost:3306/testdb"
    engine = build_engine(mysql_url)
    assert engine.dialect.name == "mysql"
    assert engine.pool._pre_ping is True
    assert engine.pool._recycle == 3600


def test_recommendation_application_and_upload_hash(tmp_path) -> None:
    from datetime import datetime, timezone
    from backend.models.domain import ModelRun, Recommendation

    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    retailer = Retailer(name="Hash Retail")
    session.add(retailer)
    session.flush()

    dataset = DatasetUpload(
        retailer_id=retailer.id,
        source_filename="catalog.csv",
        file_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    product = Product(retailer_id=retailer.id, external_id="SKU-PROMO")
    session.add_all([dataset, product])
    session.flush()

    model_run = ModelRun(
        retailer_id=retailer.id,
        dataset_id=dataset.id,
        status="completed",
        model_version="linear_dml_v1",
    )
    session.add(model_run)
    session.flush()

    recommendation = Recommendation(
        model_run_id=model_run.id,
        product_id=product.id,
        current_price=20.0,
        recommended_price=18.5,
        expected_demand=15.0,
        expected_profit=120.0,
        elasticity=-1.8,
    )
    session.add(recommendation)
    session.commit()

    assert dataset.file_hash is not None
    assert recommendation.is_applied is False
    assert recommendation.applied_at is None

    # Apply recommendation
    now = datetime.now(timezone.utc)
    recommendation.is_applied = True
    recommendation.applied_at = now
    session.commit()

    reloaded = session.get(Recommendation, recommendation.id)
    assert reloaded.is_applied is True
    assert reloaded.applied_at is not None


