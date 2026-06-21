from __future__ import annotations

from datetime import datetime, timezone
import json
from collections.abc import Mapping, Sequence
from typing import Any


def build_eval_summary(summary: dict[str, object]) -> str:
    lines = [
        "# Eval Results",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
    ]
    for key, value in summary.items():
        _append_value(lines, 0, key, value)
    return "\n".join(lines) + "\n"


def _append_value(lines: list[str], indent: int, key: str, value: Any) -> None:
    prefix = "  " * indent + f"- {key}:"
    if isinstance(value, Mapping):
        lines.append(prefix)
        for inner_key, inner_value in value.items():
            _append_value(lines, indent + 1, str(inner_key), inner_value)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if not value:
            lines.append(f"{prefix} []")
            return
        lines.append(prefix)
        for item in value:
            if isinstance(item, Mapping):
                lines.append("  " * (indent + 1) + "-")
                for inner_key, inner_value in item.items():
                    _append_value(lines, indent + 2, str(inner_key), inner_value)
            else:
                lines.append("  " * (indent + 1) + f"- {item}")
        return
    if isinstance(value, (dict, list, tuple, set)):
        lines.append(f"{prefix} {json.dumps(list(value) if isinstance(value, set) else value, ensure_ascii=False)}")
        return
    lines.append(f"{prefix} {value}")
