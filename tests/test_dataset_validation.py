from backend.services.dataset_validation import validate_dataset_csv
from fastapi.testclient import TestClient

from backend.main import app


VALID_CSV = b"""date,sku,unit_price,quantity,cost\n2025-01-01,A,10,3,4\n2025-01-02,A,11,2,4\n2025-01-03,B,8,1,3\n"""


def test_validator_resolves_common_column_aliases() -> None:
    report = validate_dataset_csv(VALID_CSV, "retailer-sales.csv")

    assert report.status == "valid"
    assert report.valid_rows == 3
    assert report.product_count == 2
    assert report.resolved_columns["product_id"] == "sku"
    assert report.resolved_columns["units_sold"] == "quantity"


def test_validator_rejects_csv_without_required_cost() -> None:
    csv_without_cost = b"date,product_id,price,units_sold\n2025-01-01,A,10,3\n"

    report = validate_dataset_csv(csv_without_cost, "incomplete.csv")

    assert report.status == "invalid"
    assert any(issue.field == "unit_cost" and issue.severity == "error" for issue in report.issues)


from backend.api.dependencies import get_current_user
from backend.models.domain import User

def test_validation_endpoint_accepts_a_csv_upload() -> None:
    app.dependency_overrides[get_current_user] = lambda: User(id="test-user-id", email="test@example.com")
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/datasets/validate",
                files={"file": ("retailer-sales.csv", VALID_CSV, "text/csv")},
            )
        assert response.status_code == 200
        assert response.json()["status"] == "valid"
    finally:
        app.dependency_overrides.clear()
