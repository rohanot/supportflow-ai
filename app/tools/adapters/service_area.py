from __future__ import annotations

import re
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ServiceFlowError
from app.core.tracing import get_trace_id
from app.db.models import ServiceArea, ToolInvocation
from app.tools.registry import is_tool_enabled
from app.tools.schemas import ServiceAreaLookupRequest, ServiceAreaLookupResponse


@dataclass(frozen=True)
class ServiceAreaRule:
    source_doc: str
    county: str
    zip_pattern: str
    region: str
    hvac: str
    plumbing: str
    electrical: str
    primary_branch: str | None
    overflow_branch: str | None
    restrictions: tuple[str, ...] = ()


RULES: tuple[ServiceAreaRule, ...] = (
    ServiceAreaRule(
        source_doc="01_service_area_north.pdf",
        county="Fairfax",
        zip_pattern="22030-22039,22041-22044",
        region="North",
        hvac="eligible",
        plumbing="eligible",
        electrical="eligible",
        primary_branch="Falls Church",
        overflow_branch="Tysons",
    ),
    ServiceAreaRule(
        source_doc="01_service_area_north.pdf",
        county="Arlington",
        zip_pattern="22201-22209,22213",
        region="North",
        hvac="eligible",
        plumbing="eligible",
        electrical="eligible",
        primary_branch="Falls Church",
        overflow_branch="Tysons",
    ),
    ServiceAreaRule(
        source_doc="01_service_area_north.pdf",
        county="Alexandria",
        zip_pattern="22301-22315",
        region="North",
        hvac="eligible",
        plumbing="eligible",
        electrical="pending",
        primary_branch="Falls Church",
        overflow_branch="Tysons",
        restrictions=("Electrical service is pending for Alexandria until Q2.",),
    ),
    ServiceAreaRule(
        source_doc="01_service_area_north.pdf",
        county="Loudoun",
        zip_pattern="20147,20148,20164,20165",
        region="North",
        hvac="eligible",
        plumbing="sub-contracted",
        electrical="not_eligible",
        primary_branch="Herndon",
        overflow_branch=None,
        restrictions=(
            "Same-day service is not available for Loudoun sub-contract work.",
            "Travel surcharge of $45 applies to addresses more than 20 miles from the nearest branch.",
        ),
    ),
    ServiceAreaRule(
        source_doc="02_service_area_central.pdf",
        county="Montgomery",
        zip_pattern="20814-20818,20832,20833",
        region="Central",
        hvac="eligible",
        plumbing="eligible",
        electrical="eligible",
        primary_branch=None,
        overflow_branch=None,
    ),
    ServiceAreaRule(
        source_doc="02_service_area_central.pdf",
        county="Howard",
        zip_pattern="21042,21043,21044,21045",
        region="Central",
        hvac="eligible",
        plumbing="eligible",
        electrical="eligible",
        primary_branch=None,
        overflow_branch=None,
    ),
    ServiceAreaRule(
        source_doc="02_service_area_central.pdf",
        county="Prince George's",
        zip_pattern="20706,20707,20708,20742",
        region="Central",
        hvac="eligible",
        plumbing="eligible",
        electrical="not_eligible",
        primary_branch=None,
        overflow_branch=None,
        restrictions=("Electrical services are not yet licensed in Prince George's County.",),
    ),
)


def _zip_in_pattern(zip_code: str, pattern: str) -> bool:
    zip_int = int(zip_code)
    for part in pattern.split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            start, end = token.split("-", 1)
            if int(start) <= zip_int <= int(end):
                return True
        elif token == zip_code:
            return True
    return False


def _structured_row_matches_zip(row: ServiceArea, zip_code: str) -> bool:
    notes = (row.restriction_notes or "").replace("–", "-")
    if notes:
        tokens = re.findall(r"\d{5}(?:-\d{5})?", notes)
        if tokens:
            return _zip_in_pattern(zip_code, ",".join(tokens))
    if row.zip_exact and row.zip_exact == zip_code:
        return True
    if row.zip_start and row.zip_end:
        return int(row.zip_start) <= int(zip_code) <= int(row.zip_end)
    return False


def _find_matching_rule(zip_code: str) -> ServiceAreaRule | None:
    for rule in RULES:
        if _zip_in_pattern(zip_code, rule.zip_pattern):
            return rule
    return None


def _status_for_service(rule: ServiceAreaRule, service_type: str) -> str:
    return getattr(rule, service_type)


def _handoff_for_status(status: str, zip_code: str) -> tuple[bool, str | None]:
    if status == "eligible":
        return False, None
    if status == "sub-contracted":
        return False, None
    if status == "pending":
        return True, f"{zip_code} is pending direct service for this service type."
    return True, f"Service is not available for this ZIP/service combination."


def _persist_lookup_trace(
    db: Session,
    *,
    request: ServiceAreaLookupRequest,
    response: ServiceAreaLookupResponse,
    latency_ms: int,
) -> None:
    db.add(
        ToolInvocation(
            trace_id=response.trace_id,
            session_id=None,
            tool_name="check_service_area",
            permission_level="read",
            requires_confirmation=False,
            validated_input_redacted=request.model_dump(mode="json"),
            output_json=response.model_dump(mode="json"),
            status="success",
            latency_ms=latency_ms,
            error_message=None,
        )
    )
    db.commit()


def check_service_area(
    db: Session,
    request: ServiceAreaLookupRequest,
    *,
    trace_id: str | None = None,
    persist_trace: bool = True,
) -> ServiceAreaLookupResponse:
    started_at = time.perf_counter()
    resolved_trace_id = trace_id or get_trace_id()
    if not is_tool_enabled(db, "check_service_area"):
        raise ServiceFlowError("Tool check_service_area is disabled.")
    rows = db.execute(select(ServiceArea).order_by(ServiceArea.id)).scalars().all()
    matching_row = next((row for row in rows if _structured_row_matches_zip(row, request.zip_code)), None)
    rule = _find_matching_rule(request.zip_code)

    if matching_row is None or rule is None:
        response = ServiceAreaLookupResponse(
            eligible=False,
            zip_code=request.zip_code,
            service_type=request.service_type,
            service_status="out_of_area",
            handoff_required=True,
            handoff_reason="Branch Manager approval required for out-of-area ZIP.",
            restrictions=["ZIPs not listed in the structured service-area table require Branch Manager approval."],
            source_doc=None,
            trace_id=resolved_trace_id,
        )
    else:
        status = _status_for_service(rule, request.service_type)
        handoff_required, handoff_reason = _handoff_for_status(status, request.zip_code)
        eligible = status in {"eligible", "sub-contracted"}
        response = ServiceAreaLookupResponse(
            eligible=eligible,
            zip_code=request.zip_code,
            service_type=request.service_type,
            region=rule.region,
            county=rule.county,
            service_status=status,
            primary_branch=rule.primary_branch,
            overflow_branch=rule.overflow_branch,
            restrictions=list(rule.restrictions),
            handoff_required=handoff_required,
            handoff_reason=handoff_reason,
            source_doc=rule.source_doc,
            trace_id=resolved_trace_id,
        )

    if persist_trace:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        _persist_lookup_trace(db, request=request, response=response, latency_ms=latency_ms)
    return response
