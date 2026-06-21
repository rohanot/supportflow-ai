from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.db.models import ConversationState as ConversationStateRow


class MeridianState(TypedDict, total=False):
    trace_id: str
    session_id: str
    user_message: str
    original_query: str | None
    clarification_question: str | None
    clarification_answer: str | None
    canonical_query: str | None
    clarification_turn_count: int
    intent: str | None
    pending_intent: str | None
    confidence: float | None
    zip_code: str | None
    region: str | None
    branch: str | None
    service_type: str | None
    job_type: str | None
    item_or_service_requested: str | None
    customer_id: str | None
    customer_info: dict | None
    preferred_date: str | None
    preferred_window: str | None
    preferred_tech: str | None
    notes: str | None
    booking_id: str | None
    retrieved_chunks: list[dict]
    citations: list[dict]
    missing_fields: list[str]
    proposed_tool_call: dict | None
    confirmation_required: bool
    confirmed_by_user: bool
    handoff_required: bool
    handoff_reason: str | None
    prompts_used: list[dict]
    graph_events: list[dict]
    debug_events: list[dict]
    final_response: str | None


class ConversationStateData(BaseModel):
    session_id: str
    pending_intent: str | None = None
    state_json: dict[str, object] = Field(default_factory=dict)
    missing_fields_json: list[object] = Field(default_factory=list)
    clarification_turn_count: int = 0
    awaiting_user_input: bool = False
    awaiting_confirmation: bool = False

    @classmethod
    def from_row(cls, row: ConversationStateRow) -> "ConversationStateData":
        return cls(
            session_id=row.session_id,
            pending_intent=row.pending_intent,
            state_json=row.state_json,
            missing_fields_json=row.missing_fields_json,
            clarification_turn_count=row.clarification_turn_count,
            awaiting_user_input=row.awaiting_user_input,
            awaiting_confirmation=row.awaiting_confirmation,
        )

    def to_state_dict(self) -> MeridianState:
        state: MeridianState = {
            "session_id": self.session_id,
            "clarification_turn_count": self.clarification_turn_count,
            "missing_fields": [str(item) for item in self.missing_fields_json],
            "retrieved_chunks": [],
            "citations": [],
            "confirmation_required": self.awaiting_confirmation,
            "confirmed_by_user": False,
            "handoff_required": False,
            "prompts_used": [],
            "graph_events": [],
            "debug_events": [],
        }
        state.update(self.state_json)
        return state

    @classmethod
    def from_state_dict(cls, session_id: str, state: MeridianState) -> "ConversationStateData":
        return cls(
            session_id=session_id,
            pending_intent=state.get("pending_intent"),
            state_json=dict(state),
            missing_fields_json=list(state.get("missing_fields", [])),
            clarification_turn_count=state.get("clarification_turn_count", 0),
            awaiting_user_input=bool(state.get("clarification_question")),
            awaiting_confirmation=bool(state.get("confirmation_required")),
        )


def build_initial_state(session_id: str, trace_id: str, user_message: str) -> ConversationStateData:
    return ConversationStateData(
        session_id=session_id,
        state_json={"session_id": session_id, "trace_id": trace_id, "user_message": user_message},
    )


def load_conversation_state(db: Session, session_id: str) -> ConversationStateData | None:
    row = db.execute(select(ConversationStateRow).where(ConversationStateRow.session_id == session_id)).scalar_one_or_none()
    if row is None:
        return None
    return ConversationStateData.from_row(row)


def save_conversation_state(db: Session, state: ConversationStateData) -> ConversationStateData:
    row = db.execute(select(ConversationStateRow).where(ConversationStateRow.session_id == state.session_id)).scalar_one_or_none()
    if row is None:
        row = ConversationStateRow(session_id=state.session_id)
        db.add(row)
    row.pending_intent = state.pending_intent
    row.state_json = state.state_json
    row.missing_fields_json = state.missing_fields_json
    row.clarification_turn_count = state.clarification_turn_count
    row.awaiting_user_input = state.awaiting_user_input
    row.awaiting_confirmation = state.awaiting_confirmation
    db.flush()
    return ConversationStateData.from_row(row)
