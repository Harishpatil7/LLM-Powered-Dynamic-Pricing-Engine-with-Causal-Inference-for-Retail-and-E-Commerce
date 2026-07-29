from backend.services.evidence_retrieval import RetrievedEvidence
from backend.services.gemini_report import build_gemini_prompt


class Document:
    title = "Causal analysis for SKU-1"
    content = "Causal run status: completed. Diagnostics: all passed."


def test_gemini_prompt_requires_grounding_and_uses_retrieved_evidence() -> None:
    prompt = build_gemini_prompt("Is the recommendation safe?", [RetrievedEvidence(Document(), 0.9)])

    assert "ONLY the evidence" in prompt
    assert "Causal analysis for SKU-1" in prompt
    assert "Is the recommendation safe?" in prompt
