from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import StateTransitionEvent, TraceEvent
from app.graph.nodes import (
    ask_clarification,
    build_canonical_query_node,
    classify_intent,
    detect_missing_slots,
    extract_slots,
    handoff,
    hybrid_rag_answer,
    persist_trace_summary,
    route_intent,
    service_area_lookup,
    trace_node,
)
from app.graph.state import ConversationStateData, build_initial_state, load_conversation_state, save_conversation_state
from app.observability.redaction import redact_value


def run_chat_graph(db: Session, *, session_id: str, trace_id: str, message: str) -> dict[str, object]:
    previous = load_conversation_state(db, session_id)
    if previous is None or not (previous.awaiting_user_input or previous.awaiting_confirmation):
        state = build_initial_state(session_id, trace_id, message).to_state_dict()
    else:
        state = previous.to_state_dict()
        state["trace_id"] = trace_id
        state["user_message"] = message

    _log_trace_event(db, trace_id, session_id, "chat", "chat_request", {"user_message": message})
    starting_state = dict(state)

    if state.get("clarification_question"):
        state = extract_slots(state)
        state = build_canonical_query_node(db, state)
        trace_node(db, state, "build_canonical_query")
        state = detect_missing_slots(state)
        if state.get("missing_fields"):
            state = ask_clarification(db, state)
            trace_node(db, state, "ask_clarification", "ask_clarification")
            if state.get("route") == "handoff":
                _log_trace_event(db, trace_id, session_id, "handoff", "handoff", {"reason": state.get("handoff_reason")})
        else:
            state = route_intent(state)
            trace_node(db, state, "route_intent", state.get("route"))
    else:
        state = classify_intent(db, state)
        trace_node(db, state, "classify_intent")
        state = extract_slots(state)
        trace_node(db, state, "extract_slots")
        state = detect_missing_slots(state)
        trace_node(db, state, "detect_missing_slots")
        if state.get("intent") == "emergency":
            state = handoff(state)
            trace_node(db, state, "handoff", "handoff")
            _log_trace_event(db, trace_id, session_id, "handoff", "handoff", {"reason": state.get("handoff_reason")})
        elif state.get("missing_fields"):
            state = ask_clarification(db, state)
            trace_node(db, state, "ask_clarification", "ask_clarification")
        else:
            state = route_intent(state)
            trace_node(db, state, "route_intent", state.get("route"))

    if state.get("route") == "hybrid_rag_answer":
        state = hybrid_rag_answer(db, state)
        trace_node(db, state, "hybrid_rag_answer", "hybrid_rag_answer")
    elif state.get("route") == "service_area_lookup":
        state = service_area_lookup(db, state)
        trace_node(db, state, "service_area_lookup", "service_area_lookup")

    trace_node(db, state, "final_response", state.get("route"))
    db.add(
        StateTransitionEvent(
            trace_id=trace_id,
            session_id=session_id,
            state_before_json=redact_value(starting_state),
            state_after_json=redact_value(dict(state)),
            route_decision=str(state.get("route") or ""),
        )
    )
    persist_trace_summary(db, state)
    saved = ConversationStateData.from_state_dict(session_id, state)
    if state.get("route") != "ask_clarification":
        saved.awaiting_user_input = False
        saved.missing_fields_json = []
        saved.state_json["clarification_question"] = None
        saved.state_json["pending_intent"] = None
    save_conversation_state(db, saved)
    db.commit()
    return state


def _log_trace_event(
    db: Session,
    trace_id: str,
    session_id: str,
    event_type: str,
    event_name: str,
    payload: dict[str, object],
) -> None:
    db.add(
        TraceEvent(
            trace_id=trace_id,
            session_id=session_id,
            event_type=event_type,
            event_name=event_name,
            event_json=redact_value(payload),
        )
    )
    db.flush()
