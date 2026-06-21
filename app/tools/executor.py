from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ServiceFlowError
from app.db.models import HITLRequest, TraceEvent
from app.observability.redaction import redact_value
from app.tools.adapters.booking import create_booking, patch_booking
from app.tools.schemas import BookingCreateRequest, BookingPatchRequest


def approve_hitl_request(db: Session, hitl_id: int) -> dict[str, object]:
    hitl = db.get(HITLRequest, hitl_id)
    if hitl is None:
        raise NotFoundError(f"HITL request {hitl_id} was not found.")
    if hitl.status != "pending":
        raise ConflictError(f"HITL request {hitl_id} is not pending.")

    payload = dict(hitl.payload_json)
    tool_name = str(payload.get("tool_name") or "")
    proposed_payload = payload.get("proposed_payload") or {}
    started_at = time.perf_counter()
    _log_hitl_event(db, hitl.trace_id, "approve_started", tool_name, payload)

    try:
        if tool_name == "create_booking":
            request = BookingCreateRequest.model_validate(proposed_payload).model_copy(
                update={"confirmed_by_user": True}
            )
            result = create_booking(db, request, trace_id=hitl.trace_id)
        elif tool_name in {"reschedule_booking", "cancel_booking", "update_notes"}:
            patch_payload = dict(proposed_payload)
            booking_id = str(patch_payload.pop("booking_id", "") or "")
            request = BookingPatchRequest.model_validate(patch_payload).model_copy(
                update={"confirmed_by_user": True}
            )
            result = patch_booking(db, booking_id, request, trace_id=hitl.trace_id)
        else:
            raise ServiceFlowError(f"Unsupported HITL tool: {tool_name}")
    except Exception as exc:
        hitl.status = "failed"
        payload["error"] = str(exc)
        hitl.payload_json = payload
        db.add(hitl)
        db.flush()
        _log_hitl_event(db, hitl.trace_id, "approve_failed", tool_name, {"error": str(exc), "payload": payload})
        db.commit()
        raise

    hitl.status = "executed"
    payload["executed_result"] = result
    hitl.payload_json = payload
    db.add(hitl)
    db.flush()
    _log_hitl_event(
        db,
        hitl.trace_id,
        "approve_executed",
        tool_name,
        {
            "hitl_id": hitl_id,
            "result": result,
            "latency_ms": int((time.perf_counter() - started_at) * 1000),
        },
    )
    db.commit()
    return {
        "hitl_request_id": hitl.id,
        "trace_id": hitl.trace_id,
        "status": "approved",
        "tool_name": tool_name,
        "result": result,
    }


def reject_hitl_request(db: Session, hitl_id: int) -> dict[str, object]:
    hitl = db.get(HITLRequest, hitl_id)
    if hitl is None:
        raise NotFoundError(f"HITL request {hitl_id} was not found.")
    if hitl.status != "pending":
        raise ConflictError(f"HITL request {hitl_id} is not pending.")

    hitl.status = "rejected"
    db.add(hitl)
    db.flush()
    _log_hitl_event(db, hitl.trace_id, "reject", str(hitl.payload_json.get("tool_name") or ""), hitl.payload_json)
    db.commit()
    return {
        "hitl_request_id": hitl.id,
        "trace_id": hitl.trace_id,
        "status": "rejected",
    }


def _log_hitl_event(db: Session, trace_id: str, event_name: str, tool_name: str, payload: dict[str, object]) -> None:
    db.add(
        TraceEvent(
            trace_id=trace_id,
            session_id=None,
            event_type="hitl",
            event_name=event_name,
            event_json=redact_value(
                {
                    "tool_name": tool_name,
                    "payload": payload,
                }
            ),
        )
    )
    db.flush()
