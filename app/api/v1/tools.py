from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.tools.adapters.service_area import check_service_area
from app.tools.registry import list_registered_tools, set_tool_enabled
from app.tools.schemas import ServiceAreaLookupRequest, ServiceAreaLookupResponse

router = APIRouter(prefix="/v1/tools", tags=["tools"])


class ToolConfigUpdate(BaseModel):
    enabled: bool


@router.get("")
def list_tools(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    return list_registered_tools(db)


@router.patch("/{tool_name}")
def update_tool(tool_name: str, payload: ToolConfigUpdate, db: Session = Depends(get_db)) -> dict[str, object]:
    return set_tool_enabled(db, tool_name, payload.enabled)


@router.post("/service-area/check", response_model=ServiceAreaLookupResponse)
def service_area_check(
    payload: ServiceAreaLookupRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> ServiceAreaLookupResponse:
    return check_service_area(
        db,
        payload,
        trace_id=getattr(request.state, "trace_id", None),
    )
