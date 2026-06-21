from __future__ import annotations

import json
from pathlib import Path

from app.evals.runner import load_jsonl, run_scenario_eval, write_eval_results


class FakeTextEmbedding:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.2 for _ in range(384)] for _ in texts]


def setup_module() -> None:
    import app.rag.embeddings

    app.rag.embeddings.TextEmbedding = FakeTextEmbedding


def test_eval_jsonl_datasets_are_loadable() -> None:
    for path in [
        Path("evals/golden_set.jsonl"),
        Path("evals/clarification_cases.jsonl"),
        Path("evals/redteam_cases.jsonl"),
    ]:
        rows = load_jsonl(path)
        assert rows
        assert all("id" in row for row in rows)


def test_scenario_eval_covers_required_cases() -> None:
    summary = run_scenario_eval()

    assert summary["total_cases"] >= 10
    assert summary["passed_cases"] >= 8
    assert summary["failed_cases"] <= 2
    assert summary["embedding_backend"] == "fastembed"
    assert summary["embedding_model"]
    assert summary["hnsw_status"]["index_name"] == "ix_chunks_embedding_hnsw"
    assert "prompt_versions" in summary
    assert summary["eval_data_excluded"] in {True, False}

    scenario_names = {item["name"] for item in summary["scenario_results"]}
    assert {
        "pricing_clarification",
        "pricing_followup",
        "service_area_clarification",
        "service_area_followup",
        "emergency_handoff",
        "no_show_fee_retrieval",
        "herndon_hours_retrieval",
        "booking_confirmation_gate",
        "approved_hitl_booking",
        "prompt_injection_guard",
        "eval_data_exclusion",
    }.issubset(scenario_names)


def test_eval_results_markdown_is_generated(tmp_path: Path) -> None:
    summary = run_scenario_eval()
    output_path = tmp_path / "eval_results.md"
    write_eval_results(output_path, summary)

    text = output_path.read_text(encoding="utf-8")
    assert "# Eval Results" in text
    assert "scenario_results" in text
    assert "prompt_versions" in text
    assert "hnsw_status" in text
    assert "eval_data_excluded" in text


def test_redteam_cases_cover_prompt_injection_and_confirmation_gate() -> None:
    rows = load_jsonl(Path("evals/redteam_cases.jsonl"))
    combined = "\n".join(json.dumps(row).lower() for row in rows)
    assert "ignore previous instructions" in combined
    assert "confirmation" in combined
