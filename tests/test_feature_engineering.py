from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.domain import DatasetUpload, Product, Retailer, SalesObservation
from backend.services.feature_engineering import build_product_panel


def test_build_product_panel_uses_only_stored_context(tmp_path) -> None:
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
    start = date(2025, 1, 1)
    for index in range(40):
        session.add(SalesObservation(
            dataset_id=dataset.id,
            product_id=product.id,
            observation_date=start + timedelta(days=index),
            price=10.0 if index % 2 == 0 else 11.0,
            units_sold=float(30 - (index % 2)),
            unit_cost=4.0,
            context={"promotion": index % 3 == 0, "event": "holiday" if index % 7 == 0 else "none"},
        ))
    session.commit()

    panel = build_product_panel(session, product.id)

    assert panel.eligible
    assert "lagged_demand_7" in panel.confounders
    assert any(field.startswith("event_") for field in panel.confounders)
    assert "weather" not in panel.confounders
    assert len(panel.frame) == 33
