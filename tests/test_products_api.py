from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.domain import DatasetUpload, Product, Retailer, SalesObservation


def test_product_observation_has_values_needed_by_frontend(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    retailer = Retailer(name="Acme Retail")
    session.add(retailer)
    session.flush()
    dataset = DatasetUpload(retailer_id=retailer.id, source_filename="sales.csv")
    product = Product(retailer_id=retailer.id, external_id="SKU-1", name="Example product")
    session.add_all([dataset, product])
    session.flush()
    session.add(SalesObservation(
        dataset_id=dataset.id, product_id=product.id, observation_date=date(2025, 1, 2),
        price=12.0, units_sold=5.0, unit_cost=6.0,
    ))
    session.commit()

    latest = session.scalar(select(SalesObservation).where(SalesObservation.product_id == product.id))
    assert latest.price == 12.0
    assert latest.units_sold == 5.0
