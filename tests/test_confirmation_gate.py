from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import BookingMock, HITLRequest
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
        "preferred_date": "2026-07-02",
        "preferred_window": "afternoon",
        "channel": "chat",
    }
    payload.update(overrides)
    return payload


def _create_confirmed_booking(client: TestClient) -> str:
    response = client.post(
        "/mock/bookings",
        json=_booking_payload(confirmed_by_user=True),
        headers={"X-Trace-Id": f"trace-confirmed-{uuid4().hex}"},
    )
    assert response.status_code == 200, response.text
    return response.json()["booking_id"]


def test_create_booking_blocked_before_confirmation() -> None:
    client = _client()
    trace_id = f"trace-create-blocked-{uuid4().hex}"
    response = client.post(
        "/mock/bookings",
        json=_booking_payload(),
        headers={"X-Trace-Id": trace_id},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "awaiting_confirmation"
    assert payload["requires_confirmation"] is True

    session = _session()
    try:
        hitl = session.execute(select(HITLRequest).where(HITLRequest.trace_id == trace_id)).scalar_one()
        assert hitl.status == "pending"
        assert session.execute(select(BookingMock).where(BookingMock.customer_id == payload["proposed_payload"]["customer_id"])).first() is None
    finally:
        session.close()


def test_reschedule_and_cancel_blocked_then_work_after_confirmation() -> None:
    client = _client()
    booking_id = _create_confirmed_booking(client)

    blocked_reschedule = client.patch(
        f"/mock/bookings/{booking_id}",
        json={"action": "reschedule", "new_date": "2026-07-05", "new_window": "morning"},
        headers={"X-Trace-Id": f"trace-reschedule-blocked-{uuid4().hex}"},
    )
    assert blocked_reschedule.status_code == 200
    assert blocked_reschedule.json()["status"] == "awaiting_confirmation"

    confirmed_reschedule = client.patch(
        f"/mock/bookings/{booking_id}",
        json={
            "action": "reschedule",
            "new_date": "2026-07-05",
            "new_window": "morning",
            "confirmed_by_user": True,
        },
        headers={"X-Trace-Id": f"trace-reschedule-confirmed-{uuid4().hex}"},
    )
    assert confirmed_reschedule.status_code == 200
    assert confirmed_reschedule.json()["status"] == "rescheduled"

    blocked_cancel = client.patch(
        f"/mock/bookings/{booking_id}",
        json={"action": "cancel", "cancel_reason": "customer request"},
        headers={"X-Trace-Id": f"trace-cancel-blocked-{uuid4().hex}"},
    )
    assert blocked_cancel.status_code == 200
    assert blocked_cancel.json()["status"] == "awaiting_confirmation"

    confirmed_cancel = client.patch(
        f"/mock/bookings/{booking_id}",
        json={"action": "cancel", "cancel_reason": "customer request", "confirmed_by_user": True},
        headers={"X-Trace-Id": f"trace-cancel-confirmed-{uuid4().hex}"},
    )
    assert confirmed_cancel.status_code == 200
    assert confirmed_cancel.json()["status"] == "cancelled"
