from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from app.db.models import ToolInvocation
from app.db.session import make_engine, make_sessionmaker
from app.main import create_app
from app.tools.adapters.service_area import check_service_area
from app.tools.schemas import ServiceAreaLookupRequest


def _session():
    engine = make_engine()
    return make_sessionmaker(engine)()


def test_20147_plumbing_is_eligible_with_loudoun_restriction() -> None:
    session = _session()
    try:
        result = check_service_area(
            session,
            ServiceAreaLookupRequest(zip_code="20147", service_type="plumbing"),
            trace_id="test-trace-20147-plumbing",
        )

        assert result.eligible is True
        assert result.service_status == "sub-contracted"
        assert result.region == "North"
        assert result.county == "Loudoun"
        assert result.primary_branch == "Herndon"
        assert "same-day service is not available" in " ".join(result.restrictions).lower()
        assert result.source_doc == "01_service_area_north.pdf"
        assert result.trace_id == "test-trace-20147-plumbing"
    finally:
        session.close()


def test_20147_electrical_is_not_eligible() -> None:
    session = _session()
    try:
        result = check_service_area(
            session,
            ServiceAreaLookupRequest(zip_code="20147", service_type="electrical"),
            trace_id="test-trace-20147-electrical",
        )

        assert result.eligible is False
        assert result.service_status == "not_eligible"
        assert result.handoff_required is True
        assert "not available" in (result.handoff_reason or "").lower()
    finally:
        session.close()


@pytest.mark.parametrize(
    ("zip_code", "service_type", "expected_county", "expected_status"),
    [
        ("22030", "hvac", "Fairfax", "eligible"),
        ("22201", "electrical", "Arlington", "eligible"),
        ("22301", "electrical", "Alexandria", "pending"),
        ("20706", "electrical", "Prince George's", "not_eligible"),
    ],
)
def test_required_structured_service_area_cases(
    zip_code: str,
    service_type: str,
    expected_county: str,
    expected_status: str,
) -> None:
    session = _session()
    try:
        result = check_service_area(
            session,
            ServiceAreaLookupRequest(zip_code=zip_code, service_type=service_type),
            trace_id=f"test-trace-{zip_code}-{service_type}",
        )

        assert result.county == expected_county
        assert result.service_status == expected_status
        assert result.source_doc
    finally:
        session.close()


def test_out_of_area_zip_returns_manager_handoff_path() -> None:
    session = _session()
    try:
        result = check_service_area(
            session,
            ServiceAreaLookupRequest(zip_code="99999", service_type="hvac"),
            trace_id="test-trace-out-of-area",
        )

        assert result.eligible is False
        assert result.handoff_required is True
        assert result.handoff_reason == "Branch Manager approval required for out-of-area ZIP."
        assert result.source_doc is None
    finally:
        session.close()


def test_invalid_zip_and_missing_service_type_validate_cleanly() -> None:
    with pytest.raises(ValidationError):
        ServiceAreaLookupRequest(zip_code="2014", service_type="hvac")

    with pytest.raises(ValidationError):
        ServiceAreaLookupRequest(zip_code="20147", service_type="")


def test_service_area_api_and_trace_persistence() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/tools/service-area/check",
        json={"zip_code": "20147", "service_type": "plumbing"},
        headers={"X-Trace-Id": "test-trace-service-area-api"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["eligible"] is True
    assert payload["trace_id"] == "test-trace-service-area-api"
    assert payload["source_doc"] == "01_service_area_north.pdf"

    session = _session()
    try:
        invocation = (
            session.execute(
                select(ToolInvocation)
                .where(
                    ToolInvocation.trace_id == "test-trace-service-area-api",
                    ToolInvocation.tool_name == "check_service_area",
                )
                .order_by(ToolInvocation.id.desc())
            )
            .scalars()
            .first()
        )
        assert invocation is not None
        assert invocation.status == "success"
        assert invocation.requires_confirmation is False
    finally:
        session.close()

