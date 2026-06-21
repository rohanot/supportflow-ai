from __future__ import annotations

from pathlib import Path


def test_eval_skeleton_files_exist() -> None:
    assert Path("evals/golden_set.jsonl").exists()
    assert Path("evals/clarification_cases.jsonl").exists()
    assert Path("evals/redteam_cases.jsonl").exists()
