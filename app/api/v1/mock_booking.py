from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.tools.adapters.booking import create_booking, lookup_booking, patch_booking
from app.tools.schemas import BookingCreateRequest, BookingPatchRequest

router = APIRouter(prefix="/mock/bookings", tags=["mock-booking"])


@router.post("")
def create_mock_booking(
    payload: BookingCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return create_booking(db, payload, trace_id=getattr(request.state, "trace_id", None))


@router.get("/{booking_id}")
def get_mock_booking(
    booking_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return lookup_booking(db, booking_id, trace_id=getattr(request.state, "trace_id", None))


@router.patch("/{booking_id}")
def patch_mock_booking(
    booking_id: str,
    payload: BookingPatchRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return patch_booking(db, booking_id, payload, trace_id=getattr(request.state, "trace_id", None))

