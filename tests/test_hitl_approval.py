from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import BookingMock, HITLRequest, ToolInvocation, TraceEvent
from app.db.session import make_engine, make_sessionmaker
from app.main import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def _session():
    return make_sessionmaker(make_engine())()


def _booking_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "customer_id": f"cust-{uuid4().hex[:8]}",
        "service_type": "plumbing",
        "job_type": "water heater replacement",
        "zip_code": "20147",
        "preferred_date": "2026-07-01",
        "preferred_window": "morning",
        "channel": "chat",
    }
    payload.update(overrides)
    return payload


def test_pending_create_booking_approval_executes_mock_post() -> None:
    client = _client()
    trace_id = f"hitl-create-{uuid4().hex}"
    blocked = client.post("/mock/bookings", json=_booking_payload(), headers={"X-Trace-Id": trace_id})
    assert blocked.status_code == 200, blocked.text
    hitl_request_id = blocked.json()["hitl_request_id"]

    approved = client.post(f"/api/v1/hitl/{hitl_request_id}/approve", headers={"X-Trace-Id": trace_id})
    assert approved.status_code == 200, approved.text
    payload = approved.json()
    assert payload["status"] == "approved"
    assert payload["tool_name"] == "create_booking"
    assert payload["result"]["status"] == "scheduled"

    session = _session()
    try:
        hitl = session.execute(select(HITLRequest).where(HITLRequest.id == hitl_request_id)).scalar_one()
        assert hitl.status == "executed"
        booking = session.execute(select(BookingMock).where(BookingMock.booking_id == payload["result"]["booking_id"])).scalar_one()
        assert booking.status == "scheduled"
    finally:
        session.close()


def test_pending_reschedule_approval_executes_mock_patch() -> None:
    client = _client()
    booking_id = client.post(
        "/mock/bookings",
        json=_booking_payload(confirmed_by_user=True),
        headers={"X-Trace-Id": f"seed-{uuid4().hex}"},
    ).json()["booking_id"]

    blocked = client.patch(
        f"/mock/bookings/{booking_id}",
        json={"action": "reschedule", "new_date": "2026-07-05", "new_window": "afternoon"},
        headers={"X-Trace-Id": f"hitl-reschedule-{uuid4().hex}"},
    )
    assert blocked.status_code == 200, blocked.text
    hitl_request_id = blocked.json()["hitl_request_id"]

    approved = client.post(f"/api/v1/hitl/{hitl_request_id}/approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()["result"]["status"] == "rescheduled"


def test_pending_cancel_approval_executes_mock_patch() -> None:
    client = _client()
    booking_id = client.post(
        "/mock/bookings",
        json=_booking_payload(confirmed_by_user=True),
        headers={"X-Trace-Id": f"seed-{uuid4().hex}"},
    ).json()["booking_id"]

    blocked = client.patch(
        f"/mock/bookings/{booking_id}",
        json={"action": "cancel", "cancel_reason": "customer request"},
        headers={"X-Trace-Id": f"hitl-cancel-{uuid4().hex}"},
    )
    assert blocked.status_code == 200, blocked.text
    hitl_request_id = blocked.json()["hitl_request_id"]

    approved = client.post(f"/api/v1/hitl/{hitl_request_id}/approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()["result"]["status"] == "cancelled"


def test_rejected_hitl_does_not_execute_tool() -> None:
    client = _client()
    blocked = client.post("/mock/bookings", json=_booking_payload(), headers={"X-Trace-Id": f"hitl-reject-{uuid4().hex}"})
    hitl_request_id = blocked.json()["hitl_request_id"]

    rejected = client.post(f"/api/v1/hitl/{hitl_request_id}/reject")
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"

    session = _session()
    try:
        hitl = session.execute(select(HITLRequest).where(HITLRequest.id == hitl_request_id)).scalar_one()
        assert hitl.status == "rejected"
        success_rows = (
            session.execute(
                select(ToolInvocation).where(ToolInvocation.trace_id == hitl.trace_id, ToolInvocation.status == "success")
            )
            .scalars()
            .all()
        )
        assert success_rows == []
    finally:
        session.close()


def test_approval_cannot_execute_twice() -> None:
    client = _client()
    blocked = client.post("/mock/bookings", json=_booking_payload(), headers={"X-Trace-Id": f"hitl-twice-{uuid4().hex}"})
    hitl_request_id = blocked.json()["hitl_request_id"]

    first = client.post(f"/api/v1/hitl/{hitl_request_id}/approve")
    assert first.status_code == 200, first.text

    second = client.post(f"/api/v1/hitl/{hitl_request_id}/approve")
    assert second.status_code == 409, second.text


def test_invalid_hitl_fails_cleanly() -> None:
    client = _client()
    response = client.post("/api/v1/hitl/999999/approve")
    assert response.status_code == 404, response.text


def test_tool_invocation_trace_exists_after_approval_execution() -> None:
    client = _client()
    trace_id = f"hitl-trace-{uuid4().hex}"
    blocked = client.post("/mock/bookings", json=_booking_payload(), headers={"X-Trace-Id": trace_id})
    hitl_request_id = blocked.json()["hitl_request_id"]

    approved = client.post(f"/api/v1/hitl/{hitl_request_id}/approve")
    assert approved.status_code == 200, approved.text

    session = _session()
    try:
        rows = (
            session.execute(
                select(ToolInvocation).where(ToolInvocation.trace_id == trace_id, ToolInvocation.tool_name == "create_booking")
            )
            .scalars()
            .all()
        )
        assert rows
        assert rows[-1].status == "success"
        assert (
            session.execute(
                select(TraceEvent).where(TraceEvent.trace_id == trace_id, TraceEvent.event_name == "approve_executed")
            )
            .scalars()
            .all()
        )
    finally:
        session.close()
