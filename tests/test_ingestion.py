from __future__ import annotations

from pathlib import Path

import pytest

from app.rag.chunking import chunk_document_text, infer_document_profile, is_default_retrieval_candidate
from app.rag.embeddings import FastEmbedBackend, fallback_embedding
from app.rag.ingestion import build_hnsw_index_ddl, extract_pdf_text, ingest_pdf_path


def test_chunking_rules_cover_pricing_faq_and_policy() -> None:
    pricing_chunks, _, _ = chunk_document_text("HVAC diagnostic fee\nHVAC repair tier T1", "pricing.pdf", "pricing")
    faq_chunks, _, _ = chunk_document_text("Q: What are your hours?\nA: Weekdays 8-5.", "faq.pdf", "faq")
    policy_chunks, _, _ = chunk_document_text("Cancellation policy\nAll appointments...", "policy.pdf", "policy")

    assert pricing_chunks
    assert faq_chunks
    assert policy_chunks


def test_pricing_chunking_keeps_row_price_and_notes() -> None:
    text = "\n".join(
        [
            "Common Services",
            "Service",
            "Price Range",
            "Notes",
            "Toilet repair / replace",
            "$175 - $450",
            "Parts included for standard models",
            "Water heater replacement (40 gal)",
            "$950 - $1,400",
            "Tankless: quote required",
        ]
    )

    pricing_chunks, _, _ = chunk_document_text(text, "04_plumbing_pricing.pdf", "pricing")
    water_heater = next(chunk for chunk in pricing_chunks if "Water heater replacement" in chunk.chunk_text)

    assert water_heater.chunk_text.startswith("Water heater replacement")
    assert "$950" in water_heater.chunk_text
    assert "$1,400" in water_heater.chunk_text
    assert "Tankless: quote required" in water_heater.chunk_text


def test_infer_document_profile_uses_filename() -> None:
    profile = infer_document_profile(Path("04_plumbing_pricing.pdf"))
    assert profile.doc_type == "pricing"


def test_fallback_embedding_has_384_dimensions() -> None:
    vector = fallback_embedding("hello world")
    assert len(vector) == 384


def test_hnsw_index_ddl_mentions_embedding() -> None:
    ddl = build_hnsw_index_ddl()
    assert "hnsw" in ddl.lower()
    assert "embedding" in ddl.lower()


def test_real_pdf_text_extraction_and_ingestion_smoke() -> None:
    pdf_path = Path("sl_docs/13_customer_messages.pdf")
    text = extract_pdf_text(pdf_path)
    assert "Herndon" in text

    backend = FastEmbedBackend(allow_fallback_embeddings=True)
    report = ingest_pdf_path(pdf_path, db=None, embedder=backend)
    assert report.chunk_count > 0
    assert report.embedding_count == report.chunk_count


def test_eval_documents_are_excluded_from_default_retrieval() -> None:
    profile = infer_document_profile(Path("13_customer_messages.pdf"))
    assert profile.doc_type == "eval_data"
    assert not is_default_retrieval_candidate(profile.doc_type)
