from __future__ import annotations

from pathlib import Path

from app.rag.chunking import infer_document_profile, is_default_retrieval_candidate


def test_customer_messages_are_marked_as_eval_data() -> None:
    profile = infer_document_profile(Path("13_customer_messages.pdf"))
    assert profile.doc_type == "eval_data"
    assert not is_default_retrieval_candidate(profile.doc_type)
