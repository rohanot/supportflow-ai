from __future__ import annotations

from dataclasses import dataclass

from app.graph.state import MeridianState


REQUIRED_FIELDS = {
    "pricing": ["item_or_service_requested"],
    "service_area_check": ["zip_code", "service_type"],
    "new_booking": ["service_type", "zip_code", "preferred_date", "preferred_window"],
    "booking_status": ["booking_id"],
    "reschedule": ["booking_id", "preferred_date", "preferred_window"],
    "cancel": ["booking_id"],
}


@dataclass(frozen=True)
class ClarificationPlan:
    missing_fields: list[str]
    question: str
    canonical_query: str | None = None
    next_route: str = "ask_clarification"


def missing_fields_for_intent(intent: str | None, state: MeridianState) -> list[str]:
    if not intent:
        return ["intent"]
    required = REQUIRED_FIELDS.get(intent, [])
    missing: list[str] = []
    for field_name in required:
        value = state.get(field_name)
        if value in (None, "", [], {}):
            missing.append(field_name)
    return missing


def clarification_question_for_missing_fields(intent: str | None, missing_fields: list[str]) -> str:
    if intent == "service_area_check" and {"zip_code", "service_type"}.issubset(set(missing_fields)):
        return "Please share your 5-digit ZIP code and the service type: HVAC, plumbing, or electrical."
    if intent == "pricing":
        return "Which service or item do you need pricing for?"
    if intent == "new_booking":
        return "What service do you need, what ZIP code is the property in, and what date/window do you prefer?"
    if intent == "booking_status":
        return "Please share your booking ID."
    if intent in {"reschedule", "cancel"}:
        return "Please share your booking ID."
    return "What detail should I clarify next?"


def build_canonical_query(original_query: str, clarification_answer: str, intent: str | None) -> str:
    if intent == "pricing":
        return f"What is the ballpark price for plumbing {clarification_answer.strip()}?".strip()
    if intent == "service_area_check":
        return f"Check service-area eligibility for {clarification_answer.strip()}."
    if intent == "new_booking":
        return f"Book a service appointment for {clarification_answer.strip()}."
    return f"{original_query.strip()} {clarification_answer.strip()}".strip()


def plan_clarification(intent: str | None, state: MeridianState) -> ClarificationPlan:
    missing = missing_fields_for_intent(intent, state)
    question = clarification_question_for_missing_fields(intent, missing)
    return ClarificationPlan(missing_fields=missing, question=question)

