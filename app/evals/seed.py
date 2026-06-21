from __future__ import annotations

import json
import re
from pathlib import Path

from app.rag.ingestion import extract_pdf_text


def extract_customer_message_cases(pdf_path: Path) -> list[dict[str, object]]:
    text = extract_pdf_text(pdf_path)
    cases: list[dict[str, object]] = []
    for index, line in enumerate([line.strip() for line in text.splitlines() if line.strip()]):
        if re.search(r"\b(book|price|service|cancel|warranty|hours|emergency)\b", line, re.IGNORECASE):
            cases.append(
                {
                    "id": f"case_{index + 1:03d}",
                    "input": line,
                    "expected_intent": "unknown",
                    "expected_route": "unknown",
                    "expected_handoff": False,
                    "expected_answer_contains": [],
                    "expected_tool": None,
                    "expected_citations": True,
                }
            )
    return cases


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=True) for row in rows) + "\n", encoding="utf-8")

