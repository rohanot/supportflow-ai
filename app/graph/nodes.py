from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import LLMUnavailableError
from app.db.models import Chunk, ClarificationEvent, GraphNodeEvent, Trace
from app.graph.clarification import (
    build_canonical_query,
    clarification_question_for_missing_fields,
    missing_fields_for_intent,
)
from app.graph.state import MeridianState
from app.llm.gateway import call_structured, call_text
from app.llm.schemas import CanonicalQueryResult, ClarificationQuestionResult, GroundedAnswerResult, RoutingDecisionResult
from app.rag.hybrid_retriever import run_hybrid_retrieval
from app.rag.schemas import RetrievalFilters, RetrievalQuery
from app.tools.adapters.service_area import check_service_area
from app.tools.schemas import ServiceAreaLookupRequest

ZIP_RE = re.compile(r"\b\d{5}\b")
SERVICE_TYPES = {"hvac", "plumbing", "electrical"}
EMERGENCY_TERMS = (
    "water is pouring",
    "flood",
    "flooding",
    "burning",
    "sparking",
    "sewage",
    "active water leak",
)


def trace_node(db: Session, state: MeridianState, node_name: str, route_decision: str | None = None) -> None:
    db.add(
        GraphNodeEvent(
            trace_id=str(state.get("trace_id") or ""),
            session_id=state.get("session_id"),
            node_name=node_name,
            input_state_summary=str(
                {
                    "intent": state.get("intent"),
                    "pending_intent": state.get("pending_intent"),
                    "missing_fields": state.get("missing_fields", []),
                }
            ),
            output_state_summary=str(
                {
                    "route": state.get("route"),
                    "canonical_query": state.get("canonical_query"),
                    "handoff_required": state.get("handoff_required"),
                }
            ),
            route_decision=route_decision,
            latency_ms=0,
            status="success",
        )
    )
    db.flush()


def classify_intent(db: Session, state: MeridianState) -> MeridianState:
    try:
        decision = call_structured(
            db=db,
            trace_id=str(state.get("trace_id") or ""),
            prompt_name="classify_intent",
            prompt_inputs={
                "user_message": state.get("user_message"),
                "conversation_state": _state_snapshot(state),
                "allowed_intents": [
                    "pricing",
                    "service_area_check",
                    "new_booking",
                    "booking_status",
                    "reschedule",
                    "cancel",
                    "faq_policy",
                    "emergency",
                ],
                "allowed_routes": [
                    "ask_clarification",
                    "service_area_lookup",
                    "hybrid_rag_answer",
                    "handoff",
                ],
            },
            response_model=RoutingDecisionResult,
        )
        state["intent"] = decision.intent
        state["route"] = decision.route
        state["missing_fields"] = decision.missing_fields
        state["canonical_query"] = decision.canonical_query
        state["clarification_question"] = decision.clarification_question
        state["handoff_required"] = decision.handoff_required
        state["handoff_reason"] = decision.handoff_reason
        state["confidence"] = decision.confidence
        if decision.normalized_slots:
            for key, value in decision.normalized_slots.items():
                if value:
                    state[key] = value
    except LLMUnavailableError:
        state["intent"] = _deterministic_intent(str(state.get("user_message") or ""))
    return state


def extract_slots(state: MeridianState) -> MeridianState:
    message = str(state.get("user_message") or "")
    lowered = message.lower()
    zip_match = ZIP_RE.search(message)
    if zip_match and not state.get("zip_code"):
        state["zip_code"] = zip_match.group(0)
    for service_type in SERVICE_TYPES:
        if service_type in lowered and not state.get("service_type"):
            state["service_type"] = service_type
    if state.get("intent") == "pricing" and not _is_ambiguous_pricing(message) and not state.get("item_or_service_requested"):
        state["item_or_service_requested"] = message.strip().rstrip(".")
        if "water heater" in lowered:
            state["service_type"] = "plumbing"
        elif "panel" in lowered:
            state["service_type"] = "electrical"
    return state


def detect_missing_slots(state: MeridianState) -> MeridianState:
    state["missing_fields"] = missing_fields_for_intent(state.get("intent"), state)
    return state


def ask_clarification(db: Session, state: MeridianState) -> MeridianState:
    turns = int(state.get("clarification_turn_count") or 0) + 1
    state["clarification_turn_count"] = turns
    if turns > 3:
        return handoff(state, "Unable to collect required information after clarification attempts.")
    missing = list(state.get("missing_fields") or [])
    question = state.get("clarification_question")
    if not question:
        try:
            result = call_structured(
                db=db,
                trace_id=str(state.get("trace_id") or ""),
                prompt_name="ask_clarification",
                prompt_inputs={
                    "intent": state.get("intent"),
                    "missing_fields": missing,
                    "conversation_state": _state_snapshot(state),
                    "user_message": state.get("user_message"),
                },
                response_model=ClarificationQuestionResult,
            )
            question = result.clarification_question
        except LLMUnavailableError:
            question = clarification_question_for_missing_fields(state.get("intent"), missing)
    state["pending_intent"] = state.get("intent")
    state["original_query"] = state.get("original_query") or state.get("user_message")
    state["clarification_question"] = question
    state["route"] = "ask_clarification"
    state["final_response"] = question
    db.add(
        ClarificationEvent(
            trace_id=str(state.get("trace_id") or ""),
            session_id=state.get("session_id"),
            original_query=str(state.get("original_query") or ""),
            missing_slots_json=missing,
            clarification_question=question,
            clarification_answer=None,
            canonical_query=None,
            next_route="ask_clarification",
        )
    )
    db.flush()
    return state


def build_canonical_query_node(db: Session, state: MeridianState) -> MeridianState:
    original_query = str(state.get("original_query") or "")
    answer = str(state.get("user_message") or "").strip().rstrip(".")
    intent = state.get("pending_intent") or state.get("intent")
    if intent == "service_area_check":
        zip_code = state.get("zip_code")
        service_type = state.get("service_type")
        state["canonical_query"] = f"Check service-area eligibility for {service_type} in ZIP {zip_code}."
    else:
        try:
            result = call_structured(
                db=db,
                trace_id=str(state.get("trace_id") or ""),
                prompt_name="build_canonical_query",
                prompt_inputs={
                    "original_query": original_query,
                    "clarification_answer": answer,
                    "intent": intent,
                    "conversation_state": _state_snapshot(state),
                },
                response_model=CanonicalQueryResult,
            )
            state["canonical_query"] = result.canonical_query
        except LLMUnavailableError:
            state["canonical_query"] = build_canonical_query(original_query, answer, intent)
    state["intent"] = intent
    state["clarification_answer"] = answer
    db.add(
        ClarificationEvent(
            trace_id=str(state.get("trace_id") or ""),
            session_id=state.get("session_id"),
            original_query=original_query,
            missing_slots_json=[],
            clarification_question=state.get("clarification_question"),
            clarification_answer=answer,
            canonical_query=state.get("canonical_query"),
            next_route="route_intent",
        )
    )
    db.flush()
    return state


def route_intent(state: MeridianState) -> MeridianState:
    if state.get("route") and state.get("route") != "ask_clarification":
        return state
    intent = state.get("intent")
    if intent == "emergency":
        state["route"] = "handoff"
    elif intent == "service_area_check":
        state["route"] = "service_area_lookup"
    elif intent in {"pricing", "faq_policy"}:
        state["route"] = "hybrid_rag_answer"
    elif intent == "new_booking":
        state["route"] = "ask_clarification"
    else:
        state["route"] = "handoff"
    return state


def hybrid_rag_answer(db: Session, state: MeridianState) -> MeridianState:
    query = str(state.get("canonical_query") or state.get("user_message") or "")
    filters = RetrievalFilters()
    response = run_hybrid_retrieval(
        db,
        RetrievalQuery(query=query, filters=filters, top_k=5, include_debug=False),
        trace_id=str(state.get("trace_id") or ""),
    )
    state["retrieved_chunks"] = [result.model_dump(mode="json") for result in response.fused_results]
    state["citations"] = [citation.model_dump(mode="json") for citation in response.citations]
    state["confidence"] = response.confidence
    state["retrieval_used"] = True
    retrieval_context = _build_retrieval_context(db, [result.chunk_id for result in response.fused_results])
    try:
        result = call_structured(
            db=db,
            trace_id=str(state.get("trace_id") or ""),
            prompt_name="grounded_answer",
            prompt_inputs={
                "user_message": state.get("user_message"),
                "query": query,
                "retrieved_context": retrieval_context,
                "citations": state.get("citations", []),
                "conversation_state": _state_snapshot(state),
            },
            response_model=GroundedAnswerResult,
        )
        state["final_response"] = _polish_grounded_answer(result.answer, query, response.citations)
        state["confidence"] = result.confidence
    except LLMUnavailableError:
        state["final_response"] = _retrieval_summary(query, response.citations)
    return state


def service_area_lookup(db: Session, state: MeridianState) -> MeridianState:
    request = ServiceAreaLookupRequest(
        zip_code=str(state.get("zip_code") or ""),
        service_type=str(state.get("service_type") or ""),
    )
    response = check_service_area(db, request, trace_id=str(state.get("trace_id") or ""))
    state["service_area"] = response.model_dump(mode="json")
    state["final_response"] = (
        f"{response.zip_code} {response.service_type} status: {response.service_status}."
    )
    return state


def handoff(state: MeridianState, reason: str | None = None) -> MeridianState:
    state["route"] = "handoff"
    state["handoff_required"] = True
    state["handoff_reason"] = reason or "Emergency or high-risk request requires human handoff."
    state["retrieval_used"] = False
    state["final_response"] = "I need to route this to a human specialist for safe handling."
    return state


def persist_trace_summary(db: Session, state: MeridianState) -> None:
    trace_id = str(state.get("trace_id") or "")
    existing = db.query(Trace).filter(Trace.trace_id == trace_id).one_or_none()
    if existing is None:
        existing = Trace(trace_id=trace_id)
        db.add(existing)
    existing.session_id = state.get("session_id")
    existing.user_message = state.get("user_message")
    existing.original_query = state.get("original_query")
    existing.clarification_question = state.get("clarification_question")
    existing.clarification_answer = state.get("clarification_answer")
    existing.canonical_query = state.get("canonical_query")
    existing.intent = state.get("intent")
    existing.pending_intent = state.get("pending_intent")
    existing.graph_path = state.get("route")
    existing.final_response = state.get("final_response")
    existing.handoff_reason = state.get("handoff_reason")
    db.flush()


def _is_ambiguous_pricing(message: str) -> bool:
    lowered = message.lower().strip()
    return lowered in {"give me the price?", "give me the price", "price?", "how much?"}


def _retrieval_summary(query: str, citations: list[Any]) -> str:
    if not citations:
        return f"I could not find grounded context for: {query}"
    first = citations[0]
    return f"I found grounded information in {first.source_doc}."


def _polish_grounded_answer(answer: str, query: str, citations: list[Any]) -> str:
    cleaned = answer.strip()
    if not cleaned or not citations:
        return cleaned
    first = citations[0]
    source_doc = getattr(first, "source_doc", None) or first.get("source_doc")
    lowered_query = query.lower()
    snippet = str(getattr(first, "snippet", None) or first.get("snippet") or "")
    price_match = re.search(r"\$[\d,]+(?:\s*[-–—]\s*\$[\d,]+)?", snippet)
    if price_match and "$" not in cleaned and any(token in lowered_query for token in ["cost", "price", "pricing"]):
        item = _pricing_item_label(lowered_query, snippet)
        return f"The {item} cost is {price_match.group(0)}, according to {source_doc}."
    if len(cleaned.split()) > 3 and str(source_doc) in cleaned:
        return cleaned
    if "no-show" in lowered_query and "$75" in cleaned:
        return f"The no-show fee is $75, according to {source_doc}."
    if len(cleaned.split()) <= 3:
        return f"The answer is {cleaned}, according to {source_doc}."
    return cleaned


def _pricing_item_label(lowered_query: str, snippet: str) -> str:
    if "water heater" in lowered_query:
        return "water heater replacement"
    if "panel upgrade" in lowered_query or "100a" in lowered_query or "200a" in lowered_query:
        return "panel upgrade"
    first_line = snippet.splitlines()[0].strip() if snippet.strip() else "service"
    return first_line.rstrip(".").lower()


def _build_retrieval_context(db: Session, chunk_ids: list[int]) -> str:
    lines: list[str] = []
    for index, chunk_id in enumerate(chunk_ids[:5], start=1):
        chunk = db.get(Chunk, chunk_id)
        if chunk is None:
            continue
        text = chunk.chunk_text[:1800]
        lines.append(f"[{index}] {chunk.source_doc} :: {chunk.section} :: {text}")
    return "\n".join(lines)


def _deterministic_intent(message: str) -> str:
    lowered = message.lower()
    if any(term in lowered for term in EMERGENCY_TERMS):
        return "emergency"
    if "service my area" in lowered or "do you service" in lowered or ZIP_RE.search(message):
        return "service_area_check"
    if "book" in lowered and "booking" not in lowered:
        return "new_booking"
    if "price" in lowered or "how much" in lowered or "panel upgrade" in lowered:
        return "pricing"
    return "faq_policy"


def _state_snapshot(state: MeridianState) -> dict[str, Any]:
    return {
        "intent": state.get("intent"),
        "pending_intent": state.get("pending_intent"),
        "missing_fields": state.get("missing_fields", []),
        "zip_code": state.get("zip_code"),
        "service_type": state.get("service_type"),
        "clarification_question": state.get("clarification_question"),
        "clarification_turn_count": state.get("clarification_turn_count", 0),
        "route": state.get("route"),
        "canonical_query": state.get("canonical_query"),
        "handoff_required": state.get("handoff_required", False),
    }
