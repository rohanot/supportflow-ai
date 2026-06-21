from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.rag.hybrid_retriever import run_hybrid_retrieval
from app.rag.schemas import RetrievalQuery, RetrievalResponse

router = APIRouter(prefix="/v1/retrieval", tags=["retrieval"])


@router.post("/test", response_model=RetrievalResponse)
def test_retrieval(
    payload: RetrievalQuery,
    request: Request,
    db: Session = Depends(get_db),
) -> RetrievalResponse:
    trace_id = getattr(request.state, "trace_id", None)
    return run_hybrid_retrieval(db=db, request=payload, trace_id=trace_id)

