from __future__ import annotations

from app.db.models import (
    BranchHours,
    BookingMock,
    ClarificationEvent,
    Chunk,
    Conversation,
    ConversationState,
    Document,
    EvalRun,
    GraphNodeEvent,
    HITLRequest,
    LLMCall,
    Message,
    PromptEvent,
    RetrievalEvent,
    ServiceArea,
    StateTransitionEvent,
    ToolInvocation,
    ToolRegistry,
    Trace,
    TraceEvent,
)


def test_required_table_names_exist() -> None:
    table_names = {
        Document.__tablename__,
        Chunk.__tablename__,
        ServiceArea.__tablename__,
        BranchHours.__tablename__,
        Conversation.__tablename__,
        Message.__tablename__,
        ConversationState.__tablename__,
        ToolRegistry.__tablename__,
        ToolInvocation.__tablename__,
        HITLRequest.__tablename__,
        BookingMock.__tablename__,
        Trace.__tablename__,
        TraceEvent.__tablename__,
        GraphNodeEvent.__tablename__,
        StateTransitionEvent.__tablename__,
        ClarificationEvent.__tablename__,
        PromptEvent.__tablename__,
        LLMCall.__tablename__,
        RetrievalEvent.__tablename__,
        EvalRun.__tablename__,
    }
    assert len(table_names) == 20


def test_chunk_embedding_column_targets_vector_storage() -> None:
    embedding_type = str(Chunk.__table__.c.embedding.type)
    assert "vector" in embedding_type.lower()

