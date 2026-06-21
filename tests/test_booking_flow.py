from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import BookingMock, ToolInvocation
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
        "notes": "40 gallon water heater",
    }
    payload.update(overrides)
    return payload


def test_lookup_booking_works_without_confirmation() -> None:
    client = _client()
    create_response = client.post(
        "/mock/bookings",
        json=_booking_payload(confirmed_by_user=True),
        headers={"X-Trace-Id": "trace-booking-lookup-create"},
    )
    assert create_response.status_code == 200, create_response.text
    booking_id = create_response.json()["booking_id"]

    lookup_response = client.get(
        f"/mock/bookings/{booking_id}",
        headers={"X-Trace-Id": "trace-booking-lookup"},
    )

    assert lookup_response.status_code == 200, lookup_response.text
    assert lookup_response.json()["booking_id"] == booking_id
    assert lookup_response.json()["status"] == "scheduled"


def test_create_booking_checks_service_area_and_persists_booking_after_confirmation() -> None:
    client = _client()
    response = client.post(
        "/mock/bookings",
        json=_booking_payload(confirmed_by_user=True),
        headers={"X-Trace-Id": "trace-booking-create-confirmed"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["booking_id"].startswith("MHS-")
    assert payload["status"] == "scheduled"
    assert payload["assigned_branch"] == "Herndon"

    session = _session()
    try:
        booking = session.execute(select(BookingMock).where(BookingMock.booking_id == payload["booking_id"])).scalar_one()
        assert booking.service_type == "plumbing"
    finally:
        session.close()


def test_create_booking_rejects_unserviceable_area() -> None:
    client = _client()
    response = client.post(
        "/mock/bookings",
        json=_booking_payload(service_type="electrical", confirmed_by_user=True),
        headers={"X-Trace-Id": "trace-booking-unserviceable"},
    )

    assert response.status_code == 400
    assert "not serviceable" in response.json()["detail"].lower()


def test_invalid_booking_payload_fails_validation() -> None:
    client = _client()
    response = client.post(
        "/mock/bookings",
        json={"service_type": "plumbing"},
        headers={"X-Trace-Id": "trace-booking-invalid"},
    )

    assert response.status_code == 422


def test_tool_invocation_trace_is_persisted_for_create_booking() -> None:
    client = _client()
    trace_id = "trace-booking-tool-invocation"
    response = client.post(
        "/mock/bookings",
        json=_booking_payload(confirmed_by_user=True),
        headers={"X-Trace-Id": trace_id},
    )
    assert response.status_code == 200, response.text

    session = _session()
    try:
        invocation = (
            session.execute(
                select(ToolInvocation)
                .where(ToolInvocation.trace_id == trace_id, ToolInvocation.tool_name == "create_booking")
                .order_by(ToolInvocation.id.desc())
            )
            .scalars()
            .first()
        )
        assert invocation is not None
        assert invocation.status == "success"
        assert invocation.requires_confirmation is True
    finally:
        session.close()

