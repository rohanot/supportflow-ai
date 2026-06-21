from __future__ import annotations

from alembic import op

from app.db.base import Base
from app.db.models import (  # noqa: F401
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

revision = "20260621_0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())

