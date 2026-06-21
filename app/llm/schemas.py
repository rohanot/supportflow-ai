from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, ConfigDict


class RoutingDecisionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal[
        "pricing",
        "service_area_check",
        "new_booking",
        "booking_status",
        "reschedule",
        "cancel",
        "faq_policy",
        "emergency",
    ]
    route: Literal["ask_clarification", "service_area_lookup", "hybrid_rag_answer", "handoff"]
    missing_fields: list[str] = Field(default_factory=list)
    canonical_query: str | None = None
    clarification_question: str | None = None
    handoff_required: bool = False
    handoff_reason: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    normalized_slots: dict[str, str] = Field(default_factory=dict)


class SlotExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zip_code: str | None = None
    service_type: str | None = None
    item_or_service_requested: str | None = None
    booking_id: str | None = None
    customer_id: str | None = None
    preferred_date: str | None = None
    preferred_window: str | None = None
    preferred_tech: str | None = None
    notes: str | None = None


class CanonicalQueryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_query: str


class ClarificationQuestionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clarification_question: str


class GroundedAnswerResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
