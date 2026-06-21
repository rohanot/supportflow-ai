from __future__ import annotations


def handoff_create(reason: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "status": "handoff_required",
        "reason": reason,
        "payload": payload or {},
    }

