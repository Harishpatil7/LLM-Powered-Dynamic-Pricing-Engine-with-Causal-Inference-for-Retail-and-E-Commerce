"""Evidence storage and LangChain vector store retrieval for grounded reports.

This module sets up the RAG retrieval layer using LangChain and semantic embeddings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session
from langchain_core.documents import Document as LCDocument
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_core.embeddings import Embeddings

from backend.config import settings
from backend.models.domain import DatasetUpload, EvidenceDocument, ModelRun, Product, Recommendation

if TYPE_CHECKING:
    from backend.models.domain import EvidenceDocument


@dataclass
class RetrievedEvidence:
    document: EvidenceDocument
    score: float


class SimpleTFIDFEmbeddings(Embeddings):
    """A lightweight local TF-IDF embedding fallback for offline testing."""
    def __init__(self) -> None:
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.vectorizer = TfidfVectorizer(stop_words="english")
        self.is_fit = False

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not self.is_fit:
            self.vectorizer.fit(texts + ["hello world", "retail product pricing model"])
            self.is_fit = True
        vectors = self.vectorizer.transform(texts).toarray()
        fixed_dim = 768
        padded = []
        for vec in vectors:
            if len(vec) >= fixed_dim:
                padded.append(vec[:fixed_dim].tolist())
            else:
                padded_one = np.pad(vec, (0, fixed_dim - len(vec)), mode="constant")
                padded.append(padded_one.tolist())
        return padded

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def get_embeddings_model() -> Embeddings:
    """Return configured Google GenAI embeddings or local TF-IDF fallback."""
    if settings.gemini_api_key:
        try:
            from langchain_google_genai import GoogleGenAIEmbeddings
            return GoogleGenAIEmbeddings(model="models/embedding-001", google_api_key=settings.gemini_api_key)
        except Exception:
            pass
    return SimpleTFIDFEmbeddings()


def _add_document(db: Session, *, retailer_id: str, product_id: str | None, source_type: str, source_id: str, title: str, content: str, metadata: dict) -> None:
    db.add(EvidenceDocument(
        retailer_id=retailer_id,
        product_id=product_id,
        source_type=source_type,
        source_id=source_id,
        title=title,
        content=content,
        metadata_json=metadata,
    ))


def add_dataset_evidence(db: Session, dataset: DatasetUpload) -> None:
    report = dataset.quality_report
    _add_document(
        db,
        retailer_id=dataset.retailer_id,
        product_id=None,
        source_type="dataset",
        source_id=dataset.id,
        title=f"Dataset quality: {dataset.source_filename}",
        content=(f"Dataset {dataset.source_filename} contains {report.get('valid_rows', 0)} valid rows, "
                 f"{report.get('product_count', 0)} products, and dates from {report.get('date_start')} to "
                 f"{report.get('date_end')}. Issues: "
                 f"{' '.join(issue.get('message', '') for issue in report.get('issues', [])) or 'none'}"),
        metadata={"quality_report": report},
    )


def add_causal_evidence(db: Session, product: Product, run: ModelRun) -> None:
    diagnostics = run.diagnostics
    checks = diagnostics.get("checks", [])
    check_text = "; ".join(
        f"{check['name']}: {'passed' if check['passed'] else 'failed'} ({check['message']})"
        for check in checks
    ) or "; ".join(diagnostics.get("limitations", []))
    _add_document(
        db,
        retailer_id=run.retailer_id,
        product_id=product.id,
        source_type="causal_run",
        source_id=run.id,
        title=f"Causal analysis for {product.external_id}",
        content=(f"Causal run status: {run.status}. Estimated price effect: {diagnostics.get('effect')}. "
                 f"Confidence interval: [{diagnostics.get('ci_lower')}, {diagnostics.get('ci_upper')}]. "
                 f"Diagnostics: {check_text}"),
        metadata=diagnostics,
    )


def add_recommendation_evidence(db: Session, recommendation: Recommendation) -> None:
    _add_document(
        db,
        retailer_id=recommendation.model_run.retailer_id,
        product_id=recommendation.product_id,
        source_type="recommendation",
        source_id=recommendation.id,
        title=f"Pricing recommendation for {recommendation.product.external_id}",
        content=(f"Current price: {recommendation.current_price}. Recommended price: "
                 f"{recommendation.recommended_price}. Expected demand: {recommendation.expected_demand}. "
                 f"Expected profit: {recommendation.expected_profit}. Rationale: {recommendation.rationale}"),
        metadata=recommendation.constraints_applied,
    )


def retrieve_evidence(db: Session, *, retailer_id: str, product_id: str, question: str, limit: int = 5) -> list[RetrievedEvidence]:
    """Retrieve semantic evidence documents using a LangChain in-memory vector store."""
    documents = list(db.scalars(select(EvidenceDocument).where(
        EvidenceDocument.retailer_id == retailer_id,
        (EvidenceDocument.product_id == product_id) | (EvidenceDocument.product_id.is_(None)),
    ).order_by(EvidenceDocument.created_at.desc())))
    
    if not documents:
        return []

    # Deduplicate keeping only the latest document of each type
    latest_by_type: dict[str, EvidenceDocument] = {}
    for document in documents:
        latest_by_type.setdefault(document.source_type, document)
    deduplicated_docs = list(latest_by_type.values())

    # Build LangChain Documents
    lc_docs = []
    for doc in deduplicated_docs:
        lc_docs.append(LCDocument(
            page_content=doc.content,
            metadata={"id": doc.id, "title": doc.title, "source_type": doc.source_type}
        ))

    # Initialize Embeddings and Vector Store
    embeddings = get_embeddings_model()
    vector_store = InMemoryVectorStore.from_documents(lc_docs, embeddings)

    # Perform search
    results = vector_store.similarity_search_with_score(question, k=limit)

    # Map results back to db records
    retrieved = []
    db_docs_by_id = {doc.id: doc for doc in deduplicated_docs}
    for lc_doc, score in results:
        doc_id = lc_doc.metadata.get("id")
        db_doc = db_docs_by_id.get(doc_id)
        if db_doc:
            # Scale distance metric to a standard score
            retrieved.append(RetrievedEvidence(document=db_doc, score=float(score)))

    return retrieved


def build_grounded_preview(evidence: list[RetrievedEvidence]) -> tuple[str, str | None]:
    """A deterministic, non-LLM report used until an LLM provider is configured."""

    causal = next((item.document for item in evidence if item.document.source_type == "causal_run"), None)
    recommendation = next((item.document for item in evidence if item.document.source_type == "recommendation"), None)
    if causal is None:
        return "No causal analysis evidence is available for this product.", "Run causal analysis before requesting a report."
    answer = f"Verified causal evidence: {causal.content}"
    if recommendation:
        answer += f" Verified optimisation evidence: {recommendation.content}"
        return answer, None
    return answer, "No verified price recommendation is available; this preview does not recommend a price."
