from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request) -> dict[str, object]:
    return {
        "status": "ok",
        "trace_id": getattr(request.state, "trace_id", None),
    }

