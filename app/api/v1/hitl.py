from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import HITLRequest
from app.db.session import get_db
from app.tools.executor import approve_hitl_request, reject_hitl_request

router = APIRouter(prefix="/v1/hitl", tags=["hitl"])


@router.get("/pending")
def pending_hitl(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    rows = db.execute(select(HITLRequest).where(HITLRequest.status == "pending").order_by(HITLRequest.id.desc())).scalars().all()
    return [
        {
            "id": row.id,
            "trace_id": row.trace_id,
            "reason": row.reason,
            "payload": row.payload_json,
            "status": row.status,
        }
        for row in rows
    ]


@router.post("/{hitl_id}/approve")
def approve_hitl(hitl_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    return approve_hitl_request(db, hitl_id)


@router.post("/{hitl_id}/reject")
def reject_hitl(hitl_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    return reject_hitl_request(db, hitl_id)
