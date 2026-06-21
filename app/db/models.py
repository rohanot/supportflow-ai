from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import vector_type


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=False), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=False), default=utc_now, onupdate=utc_now, nullable=False
    )


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    source_doc: Mapped[str] = mapped_column(sa.String(255), nullable=False, unique=True)
    title: Mapped[str | None] = mapped_column(sa.String(500))
    doc_type: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    source_path: Mapped[str | None] = mapped_column(sa.String(500))
    region: Mapped[str | None] = mapped_column(sa.String(100))
    branch: Mapped[str | None] = mapped_column(sa.String(100))
    service_type: Mapped[str | None] = mapped_column(sa.String(100))
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_text: Mapped[str] = mapped_column(sa.Text, nullable=False)
    source_doc: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    page_number: Mapped[int | None] = mapped_column(sa.Integer)
    section: Mapped[str | None] = mapped_column(sa.String(255))
    doc_type: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    region: Mapped[str | None] = mapped_column(sa.String(100))
    branch: Mapped[str | None] = mapped_column(sa.String(100))
    service_type: Mapped[str | None] = mapped_column(sa.String(100))
    policy_type: Mapped[str | None] = mapped_column(sa.String(100))
    effective_date: Mapped[str | None] = mapped_column(sa.String(32))
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR)
    embedding: Mapped[object | None] = mapped_column(vector_type(384))
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=False), default=utc_now, nullable=False)


class ServiceArea(Base, TimestampMixin):
    __tablename__ = "service_areas"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    region: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    county: Mapped[str | None] = mapped_column(sa.String(100))
    zip_start: Mapped[str | None] = mapped_column(sa.String(10))
    zip_end: Mapped[str | None] = mapped_column(sa.String(10))
    zip_exact: Mapped[str | None] = mapped_column(sa.String(10))
    hvac_status: Mapped[str | None] = mapped_column(sa.String(50))
    plumbing_status: Mapped[str | None] = mapped_column(sa.String(50))
    electrical_status: Mapped[str | None] = mapped_column(sa.String(50))
    primary_branch: Mapped[str | None] = mapped_column(sa.String(100))
    overflow_branch: Mapped[str | None] = mapped_column(sa.String(100))
    restriction_notes: Mapped[str | None] = mapped_column(sa.Text)
    source_doc: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    source_chunk_id: Mapped[int | None] = mapped_column(sa.ForeignKey("chunks.id", ondelete="SET NULL"))


class BranchHours(Base, TimestampMixin):
    __tablename__ = "branch_hours"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    branch: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    day_of_week: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    opens_at: Mapped[str | None] = mapped_column(sa.String(16))
    closes_at: Mapped[str | None] = mapped_column(sa.String(16))
    timezone: Mapped[str | None] = mapped_column(sa.String(64))
    source_doc: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    source_chunk_id: Mapped[int | None] = mapped_column(sa.ForeignKey("chunks.id", ondelete="SET NULL"))
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(sa.String(128), nullable=False, unique=True)
    current_intent: Mapped[str | None] = mapped_column(sa.String(100))
    pending_intent: Mapped[str | None] = mapped_column(sa.String(100))
    trace_id: Mapped[str | None] = mapped_column(sa.String(64))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=False), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=False), default=utc_now, onupdate=utc_now, nullable=False
    )


class Message(Base, TimestampMixin):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    content: Mapped[str] = mapped_column(sa.Text, nullable=False)
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)


class ConversationState(Base):
    __tablename__ = "conversation_state"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(sa.String(128), nullable=False, unique=True)
    state_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    pending_intent: Mapped[str | None] = mapped_column(sa.String(100))
    missing_fields_json: Mapped[list[object]] = mapped_column(JSONB, default=list, nullable=False)
    clarification_turn_count: Mapped[int] = mapped_column(sa.Integer, default=0, nullable=False)
    awaiting_user_input: Mapped[bool] = mapped_column(sa.Boolean, default=False, nullable=False)
    awaiting_confirmation: Mapped[bool] = mapped_column(sa.Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=False), default=utc_now, onupdate=utc_now, nullable=False
    )


class ToolRegistry(Base, TimestampMixin):
    __tablename__ = "tool_registry"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    tool_name: Mapped[str] = mapped_column(sa.String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(sa.Text)
    permission_level: Mapped[str | None] = mapped_column(sa.String(50))
    requires_confirmation: Mapped[bool] = mapped_column(sa.Boolean, default=False, nullable=False)
    schema_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)


class ToolInvocation(Base, TimestampMixin):
    __tablename__ = "tool_invocations"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    trace_id: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(sa.String(128))
    tool_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    permission_level: Mapped[str | None] = mapped_column(sa.String(50))
    requires_confirmation: Mapped[bool] = mapped_column(sa.Boolean, default=False, nullable=False)
    validated_input_redacted: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    output_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(sa.Integer)
    error_message: Mapped[str | None] = mapped_column(sa.Text)


class HITLRequest(Base, TimestampMixin):
    __tablename__ = "hitl_requests"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    trace_id: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(sa.String(128))
    reason: Mapped[str] = mapped_column(sa.Text, nullable=False)
    payload_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(sa.String(50), default="pending", nullable=False)


class BookingMock(Base, TimestampMixin):
    __tablename__ = "bookings_mock"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    booking_id: Mapped[str] = mapped_column(sa.String(64), nullable=False, unique=True)
    customer_id: Mapped[str | None] = mapped_column(sa.String(128))
    customer_info_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    service_type: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    job_type: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    zip_code: Mapped[str] = mapped_column(sa.String(10), nullable=False)
    preferred_date: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    preferred_window: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    preferred_tech: Mapped[str | None] = mapped_column(sa.String(100))
    notes: Mapped[str | None] = mapped_column(sa.Text)
    channel: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    assigned_branch: Mapped[str | None] = mapped_column(sa.String(100))
    appointment_window: Mapped[str | None] = mapped_column(sa.String(64))
    tech_name: Mapped[str | None] = mapped_column(sa.String(100))
    confirmation_sent: Mapped[bool] = mapped_column(sa.Boolean, default=False, nullable=False)
    fee_applied: Mapped[bool] = mapped_column(sa.Boolean, default=False, nullable=False)
    waiver_used: Mapped[bool] = mapped_column(sa.Boolean, default=False, nullable=False)
    invoice_total: Mapped[float | None] = mapped_column(sa.Numeric(10, 2))


class Trace(Base, TimestampMixin):
    __tablename__ = "traces"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    trace_id: Mapped[str] = mapped_column(sa.String(64), nullable=False, unique=True)
    session_id: Mapped[str | None] = mapped_column(sa.String(128))
    user_message: Mapped[str | None] = mapped_column(sa.Text)
    original_query: Mapped[str | None] = mapped_column(sa.Text)
    clarification_question: Mapped[str | None] = mapped_column(sa.Text)
    clarification_answer: Mapped[str | None] = mapped_column(sa.Text)
    canonical_query: Mapped[str | None] = mapped_column(sa.Text)
    intent: Mapped[str | None] = mapped_column(sa.String(100))
    pending_intent: Mapped[str | None] = mapped_column(sa.String(100))
    graph_path: Mapped[str | None] = mapped_column(sa.Text)
    final_response: Mapped[str | None] = mapped_column(sa.Text)
    handoff_reason: Mapped[str | None] = mapped_column(sa.Text)


class TraceEvent(Base, TimestampMixin):
    __tablename__ = "trace_events"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    trace_id: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(sa.String(128))
    event_type: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    event_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    event_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)


class GraphNodeEvent(Base, TimestampMixin):
    __tablename__ = "graph_node_events"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    trace_id: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(sa.String(128))
    node_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    input_state_summary: Mapped[str | None] = mapped_column(sa.Text)
    output_state_summary: Mapped[str | None] = mapped_column(sa.Text)
    route_decision: Mapped[str | None] = mapped_column(sa.String(100))
    latency_ms: Mapped[int | None] = mapped_column(sa.Integer)
    status: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    error_message: Mapped[str | None] = mapped_column(sa.Text)


class StateTransitionEvent(Base, TimestampMixin):
    __tablename__ = "state_transition_events"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    trace_id: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(sa.String(128))
    state_before_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    state_after_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    route_decision: Mapped[str | None] = mapped_column(sa.String(100))


class ClarificationEvent(Base, TimestampMixin):
    __tablename__ = "clarification_events"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    trace_id: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(sa.String(128))
    original_query: Mapped[str] = mapped_column(sa.Text, nullable=False)
    missing_slots_json: Mapped[list[object]] = mapped_column(JSONB, default=list, nullable=False)
    clarification_question: Mapped[str | None] = mapped_column(sa.Text)
    clarification_answer: Mapped[str | None] = mapped_column(sa.Text)
    canonical_query: Mapped[str | None] = mapped_column(sa.Text)
    next_route: Mapped[str | None] = mapped_column(sa.String(100))


class PromptEvent(Base, TimestampMixin):
    __tablename__ = "prompt_events"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    trace_id: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    prompt_name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    prompt_version: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    prompt_inputs_redacted: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    rendered_prompt_preview: Mapped[str | None] = mapped_column(sa.Text)
    model: Mapped[str | None] = mapped_column(sa.String(100))
    provider: Mapped[str | None] = mapped_column(sa.String(100))


class LLMCall(Base, TimestampMixin):
    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    trace_id: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    prompt_name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    prompt_version: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    model: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    provider: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    temperature: Mapped[float | None] = mapped_column(sa.Float)
    input_tokens: Mapped[int | None] = mapped_column(sa.Integer)
    output_tokens: Mapped[int | None] = mapped_column(sa.Integer)
    estimated_cost: Mapped[float | None] = mapped_column(sa.Numeric(10, 4))
    latency_ms: Mapped[int | None] = mapped_column(sa.Integer)
    status: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    error_message: Mapped[str | None] = mapped_column(sa.Text)


class RetrievalEvent(Base, TimestampMixin):
    __tablename__ = "retrieval_events"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    trace_id: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(sa.String(128))
    query: Mapped[str] = mapped_column(sa.Text, nullable=False)
    canonical_query: Mapped[str | None] = mapped_column(sa.Text)
    filters_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    dense_top_k: Mapped[int | None] = mapped_column(sa.Integer)
    lexical_top_k: Mapped[int | None] = mapped_column(sa.Integer)
    fused_top_k: Mapped[int | None] = mapped_column(sa.Integer)
    dense_results_json: Mapped[list[object]] = mapped_column(JSONB, default=list, nullable=False)
    lexical_results_json: Mapped[list[object]] = mapped_column(JSONB, default=list, nullable=False)
    fused_results_json: Mapped[list[object]] = mapped_column(JSONB, default=list, nullable=False)
    selected_context: Mapped[str | None] = mapped_column(sa.Text)
    citation_ids_json: Mapped[list[object]] = mapped_column(JSONB, default=list, nullable=False)
    retrieval_confidence: Mapped[float | None] = mapped_column(sa.Float)


class EvalRun(Base, TimestampMixin):
    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    eval_name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    prompt_versions_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    total_cases: Mapped[int | None] = mapped_column(sa.Integer)
    passed_cases: Mapped[int | None] = mapped_column(sa.Integer)
    failed_cases: Mapped[int | None] = mapped_column(sa.Integer)
    metrics_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    results_path: Mapped[str | None] = mapped_column(sa.String(500))
