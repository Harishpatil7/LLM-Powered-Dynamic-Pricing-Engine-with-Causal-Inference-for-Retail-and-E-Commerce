from datetime import datetime, timezone

from backend.services.evidence_retrieval import RetrievedEvidence, build_grounded_preview


class Document:
    def __init__(self, source_type, content):
        self.source_type = source_type
        self.content = content


def test_grounded_preview_does_not_invent_a_recommendation() -> None:
    evidence = [RetrievedEvidence(Document("causal_run", "Causal run status: completed. Diagnostics: subset failed."), 0.9)]

    answer, warning = build_grounded_preview(evidence)

    assert "Causal run status" in answer
    assert warning is not None


from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database import Base
from backend.models.domain import EvidenceDocument
from backend.services.evidence_retrieval import retrieve_evidence

def test_retrieve_evidence_semantic_fallback(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    doc1 = EvidenceDocument(
        retailer_id="ret-1",
        product_id="prod-1",
        source_type="causal_run",
        source_id="run-1",
        title="Causal Run",
        content="Causal run status: completed. Diagnostics: placebo passed. elasticity is -2.4.",
        metadata_json={}
    )
    doc2 = EvidenceDocument(
        retailer_id="ret-1",
        product_id="prod-1",
        source_type="recommendation",
        source_id="rec-1",
        title="Pricing Recommendation",
        content="Optimal recommended price is 9.99 with expected profit of 150.",
        metadata_json={}
    )
    session.add_all([doc1, doc2])
    session.commit()

    results = retrieve_evidence(session, retailer_id="ret-1", product_id="prod-1", question="What is the recommended price?")
    assert len(results) > 0
    # The top document matching semantic similarity search should be pricing recommendation
    assert results[0].document.source_type == "recommendation"
