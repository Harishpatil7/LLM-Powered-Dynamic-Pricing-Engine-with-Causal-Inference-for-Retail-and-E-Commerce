from datetime import datetime, timedelta, timezone

from backend.models.domain import EvidenceDocument


def test_newest_evidence_should_replace_older_evidence_of_the_same_type() -> None:
    older = EvidenceDocument(source_type="recommendation", title="Old", content="old", retailer_id="r", source_id="1")
    newer = EvidenceDocument(source_type="recommendation", title="New", content="new", retailer_id="r", source_id="2")
    older.created_at = datetime.now(timezone.utc) - timedelta(days=1)
    newer.created_at = datetime.now(timezone.utc)
    latest_by_type = {}
    for document in sorted([older, newer], key=lambda item: item.created_at, reverse=True):
        latest_by_type.setdefault(document.source_type, document)

    assert latest_by_type["recommendation"].title == "New"
