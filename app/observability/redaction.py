from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any


def redact_text(text: str) -> str:
    text = re.sub(r"\b\d{5}\b", "[ZIP]", text)
    text = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[SSN]", text)
    return text


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {key: redact_value(inner) for key, inner in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [redact_value(item) for item in value]
    return value
