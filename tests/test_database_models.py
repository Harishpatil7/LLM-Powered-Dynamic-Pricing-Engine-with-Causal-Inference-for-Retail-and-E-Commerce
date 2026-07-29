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
