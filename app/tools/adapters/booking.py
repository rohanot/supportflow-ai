from __future__ import annotations

import time
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ServiceFlowError
from app.core.tracing import get_trace_id
from app.db.models import BookingMock, HITLRequest, ToolInvocation
from app.tools.adapters.service_area import check_service_area
from app.tools.registry import is_tool_enabled
from app.tools.schemas import BookingCreateRequest, BookingPatchRequest, ServiceAreaLookupRequest


def create_booking(db: Session, request: BookingCreateRequest, *, trace_id: str | None = None) -> dict[str, object]:
    started_at = time.perf_counter()
    resolved_trace_id = trace_id or get_trace_id()
    _ensure_tool_enabled(db, "create_booking")
    if not request.confirmed_by_user:
        response = _pending_confirmation(db, resolved_trace_id, "create_booking", request.model_dump(mode="json"))
        _persist_tool_invocation(db, resolved_trace_id, "create_booking", request.model_dump(mode="json"), response, "pending_confirmation", started_at)
        return response

    service_area = check_service_area(
        db,
        ServiceAreaLookupRequest(zip_code=request.zip_code, service_type=request.service_type),
        trace_id=resolved_trace_id,
        persist_trace=False,
    )
    if not service_area.eligible:
        raise ServiceFlowError(f"ZIP/service combination is not serviceable: {service_area.handoff_reason}")

    booking_id = f"MHS-{uuid4().hex[:8].upper()}"
    booking = BookingMock(
        booking_id=booking_id,
        customer_id=request.customer_id,
        customer_info_json=request.customer_info or {},
        service_type=request.service_type,
        job_type=request.job_type,
        zip_code=request.zip_code,
        preferred_date=request.preferred_date,
        preferred_window=request.preferred_window,
        preferred_tech=request.preferred_tech,
        notes=request.notes,
        channel=request.channel,
        status="scheduled",
        assigned_branch=service_area.primary_branch,
        appointment_window=request.preferred_window,
        tech_name=None,
        confirmation_sent=True,
    )
    db.add(booking)
    db.flush()
    response = {
        "booking_id": booking_id,
        "status": "scheduled",
        "assigned_branch": service_area.primary_branch,
        "appointment_window": request.preferred_window,
        "tech_name": None,
        "confirmation_sent": True,
    }
    _persist_tool_invocation(db, resolved_trace_id, "create_booking", request.model_dump(mode="json"), response, "success", started_at)
    return response


def lookup_booking(db: Session, booking_id: str, *, trace_id: str | None = None) -> dict[str, object]:
    started_at = time.perf_counter()
    resolved_trace_id = trace_id or get_trace_id()
    _ensure_tool_enabled(db, "lookup_booking")
    booking = _get_booking(db, booking_id)
    response = {
        "booking_id": booking.booking_id,
        "status": booking.status,
        "service_type": booking.service_type,
        "job_type": booking.job_type,
        "appointment_window": booking.appointment_window,
        "tech_name": booking.tech_name,
        "tech_eta_minutes": None,
        "notes": booking.notes,
        "invoice_total": float(booking.invoice_total) if booking.invoice_total is not None else None,
    }
    _persist_tool_invocation(db, resolved_trace_id, "lookup_booking", {"booking_id": booking_id}, response, "success", started_at, requires_confirmation=False)
    return response


def patch_booking(db: Session, booking_id: str, request: BookingPatchRequest, *, trace_id: str | None = None) -> dict[str, object]:
    started_at = time.perf_counter()
    resolved_trace_id = trace_id or get_trace_id()
    tool_name = f"{request.action}_booking" if request.action != "update_notes" else "update_notes"
    _ensure_tool_enabled(db, tool_name)
    payload = request.model_dump(mode="json")
    payload["booking_id"] = booking_id
    if not request.confirmed_by_user:
        response = _pending_confirmation(db, resolved_trace_id, tool_name, payload)
        _persist_tool_invocation(db, resolved_trace_id, tool_name, payload, response, "pending_confirmation", started_at)
        return response

    booking = _get_booking(db, booking_id)
    if request.action == "reschedule":
        booking.status = "rescheduled"
        booking.preferred_date = request.new_date or booking.preferred_date
        booking.preferred_window = request.new_window or booking.preferred_window
        booking.appointment_window = request.new_window
        response = {
            "booking_id": booking.booking_id,
            "status": "rescheduled",
            "fee_applied": False,
            "waiver_used": False,
            "new_appointment_window": request.new_window,
        }
    elif request.action == "cancel":
        booking.status = "cancelled"
        response = {
            "booking_id": booking.booking_id,
            "status": "cancelled",
            "fee_applied": False,
            "waiver_used": False,
            "new_appointment_window": None,
        }
    else:
        booking.notes = request.notes
        response = {
            "booking_id": booking.booking_id,
            "status": booking.status,
            "fee_applied": False,
            "waiver_used": False,
            "new_appointment_window": booking.appointment_window,
        }
    db.flush()
    _persist_tool_invocation(db, resolved_trace_id, tool_name, payload, response, "success", started_at)
    return response


def _get_booking(db: Session, booking_id: str) -> BookingMock:
    booking = db.execute(select(BookingMock).where(BookingMock.booking_id == booking_id)).scalar_one_or_none()
    if booking is None:
        raise NotFoundError(f"Booking {booking_id} was not found.")
    return booking


def _ensure_tool_enabled(db: Session, tool_name: str) -> None:
    if not is_tool_enabled(db, tool_name):
        raise ServiceFlowError(f"Tool {tool_name} is disabled.")


def _pending_confirmation(db: Session, trace_id: str, tool_name: str, payload: dict[str, object]) -> dict[str, object]:
    request = HITLRequest(
        trace_id=trace_id,
        session_id=None,
        reason=f"{tool_name} requires explicit confirmation.",
        payload_json={"tool_name": tool_name, "proposed_payload": payload},
        status="pending",
    )
    db.add(request)
    db.flush()
    return {
        "status": "awaiting_confirmation",
        "requires_confirmation": True,
        "hitl_request_id": request.id,
        "proposed_payload": payload,
    }


def _persist_tool_invocation(
    db: Session,
    trace_id: str,
    tool_name: str,
    input_payload: dict[str, object],
    output_payload: dict[str, object],
    status: str,
    started_at: float,
    *,
    requires_confirmation: bool = True,
) -> None:
    db.add(
        ToolInvocation(
            trace_id=trace_id,
            session_id=None,
            tool_name=tool_name,
            permission_level="write" if requires_confirmation else "read",
            requires_confirmation=requires_confirmation,
            validated_input_redacted=input_payload,
            output_json=output_payload,
            status=status,
            latency_ms=int((time.perf_counter() - started_at) * 1000),
            error_message=None,
        )
    )
    db.commit()
