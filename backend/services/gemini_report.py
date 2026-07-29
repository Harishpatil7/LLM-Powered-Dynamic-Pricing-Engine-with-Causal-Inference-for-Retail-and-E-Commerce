"""Gemini generation constrained to evidence retrieved by the local RAG layer."""

from __future__ import annotations

from backend.config import settings
from backend.services.evidence_retrieval import RetrievedEvidence


def build_gemini_prompt(question: str, evidence: list[RetrievedEvidence]) -> str:
    sources = "\n\n".join(
        f"SOURCE {index + 1}: {item.document.title}\n{item.document.content}"
        for index, item in enumerate(evidence)
    )
    return f"""You are a retail pricing report assistant.
Answer the manager's question using ONLY the evidence sources below.
Do not invent prices, profit, causal effects, diagnostics, competitor context, or data fields.
If no verified recommendation source exists, explicitly state that no price recommendation is available.
If any diagnostic is failed or blocked, explain that optimisation should not be acted on.
Write a concise report with these plain-text headings on separate lines: Summary, Evidence, Recommendation status, and Limitations.
Use plain text only: do not use Markdown symbols such as #, *, or ---.
Do not claim that you performed calculations yourself.

Manager question: {question}

Verified evidence:
{sources}"""


def generate_gemini_report(question: str, evidence: list[RetrievedEvidence]) -> str:
    if not settings.gemini_api_key:
        raise RuntimeError("Gemini is not configured. Set GEMINI_API_KEY in .env and restart the backend.")
    from google import genai

    client = genai.Client(api_key=settings.gemini_api_key)
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=build_gemini_prompt(question, evidence),
    )
    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("Gemini returned an empty report.")
    return text
