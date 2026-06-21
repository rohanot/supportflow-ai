from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.graph.build_graph import run_chat_graph

router = APIRouter(prefix="/v1/chat", tags=["chat"])


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    trace_id: str
    session_id: str
    message: str
    route: str
    intent: str | None = None
    canonical_query: str | None = None
    clarification_question: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    citations: list[dict[str, object]] = Field(default_factory=list)
    retrieval_used: bool = False
    handoff_required: bool = False
    handoff_reason: str | None = None
    service_area: dict[str, object] | None = None


@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequest, request: Request, db: Session = Depends(get_db)) -> ChatResponse:
    trace_id = getattr(request.state, "trace_id", None)
    state = run_chat_graph(db, session_id=payload.session_id, trace_id=trace_id, message=payload.message)
    return ChatResponse(
        trace_id=str(state.get("trace_id") or ""),
        session_id=payload.session_id,
        message=str(state.get("final_response") or ""),
        route=str(state.get("route") or ""),
        intent=state.get("intent"),
        canonical_query=state.get("canonical_query"),
        clarification_question=state.get("clarification_question"),
        missing_fields=[str(item) for item in state.get("missing_fields", [])],
        citations=[dict(item) for item in state.get("citations", [])],
        retrieval_used=bool(state.get("retrieval_used", False)),
        handoff_required=bool(state.get("handoff_required", False)),
        handoff_reason=state.get("handoff_reason"),
        service_area=state.get("service_area"),
    )

