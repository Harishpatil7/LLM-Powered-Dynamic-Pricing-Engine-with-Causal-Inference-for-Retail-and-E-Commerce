from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.domain import DatasetUpload, Product, Retailer, SalesObservation
from backend.schemas.datasets import DatasetColumnMapping
from backend.services.dataset_ingestion import persist_validated_dataset


CSV = b"""date,sku,unit_price,quantity,cost,store,event\n2025-01-01,A,10,3,4,S1,holiday\n2025-01-02,A,11,2,4,S1,none\n2025-01-01,B,8,1,3,S1,holiday\n"""


def test_persist_validated_dataset_creates_traceable_records(tmp_path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    retailer = Retailer(name="Acme Retail")
    session.add(retailer)
    session.commit()
    monkeypatch.setattr("backend.services.dataset_ingestion.UPLOAD_ROOT", tmp_path / "uploads")

    dataset = persist_validated_dataset(
        db=session,
        retailer=retailer,
        content=CSV,
        filename="sales.csv",
        mapping=DatasetColumnMapping(),
    )
    session.commit()

    assert (tmp_path / "uploads" / retailer.id / f"{dataset.id}.csv").exists()
    assert session.scalar(select(func.count()).select_from(DatasetUpload)) == 1
    assert session.scalar(select(func.count()).select_from(Product)) == 2
    assert session.scalar(select(func.count()).select_from(SalesObservation)) == 3
