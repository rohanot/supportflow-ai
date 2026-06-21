from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.models import ToolRegistry


REGISTERED_TOOLS: tuple[dict[str, object], ...] = (
    {
        "tool_name": "check_service_area",
        "description": "Deterministically checks ZIP/service coverage from structured service-area rows.",
        "permission_level": "read",
        "requires_confirmation": False,
        "enabled": True,
    },
    {
        "tool_name": "lookup_booking",
        "description": "Looks up an existing mock booking.",
        "permission_level": "read",
        "requires_confirmation": False,
        "enabled": True,
    },
    {
        "tool_name": "create_booking",
        "description": "Creates a mock service booking after explicit confirmation.",
        "permission_level": "write",
        "requires_confirmation": True,
        "enabled": True,
    },
    {
        "tool_name": "reschedule_booking",
        "description": "Reschedules a mock booking after explicit confirmation.",
        "permission_level": "write",
        "requires_confirmation": True,
        "enabled": True,
    },
    {
        "tool_name": "cancel_booking",
        "description": "Cancels a mock booking after explicit confirmation.",
        "permission_level": "write",
        "requires_confirmation": True,
        "enabled": True,
    },
)


def list_registered_tools(db: Session | None = None) -> list[dict[str, object]]:
    defaults = [dict(tool) for tool in REGISTERED_TOOLS]
    if db is None:
        return defaults

    ensure_tool_registry(db)
    rows = db.execute(select(ToolRegistry)).scalars().all()
    rows_by_name = {row.tool_name: row for row in rows}
    tools: list[dict[str, object]] = []
    for tool in defaults:
        row = rows_by_name.get(str(tool["tool_name"]))
        if row is None:
            tools.append(tool)
            continue
        schema = row.schema_json or {}
        tools.append(
            {
                "tool_name": row.tool_name,
                "description": row.description,
                "permission_level": row.permission_level,
                "requires_confirmation": row.requires_confirmation,
                "enabled": bool(schema.get("enabled", True)),
            }
        )
    return tools


def ensure_tool_registry(db: Session) -> None:
    existing = {
        row.tool_name
        for row in db.execute(select(ToolRegistry).where(ToolRegistry.tool_name.in_(_tool_names()))).scalars().all()
    }
    for tool in REGISTERED_TOOLS:
        if str(tool["tool_name"]) in existing:
            continue
        db.add(
            ToolRegistry(
                tool_name=str(tool["tool_name"]),
                description=str(tool["description"]),
                permission_level=str(tool["permission_level"]),
                requires_confirmation=bool(tool["requires_confirmation"]),
                schema_json={"enabled": bool(tool.get("enabled", True))},
            )
        )
    db.commit()


def set_tool_enabled(db: Session, tool_name: str, enabled: bool) -> dict[str, object]:
    ensure_tool_registry(db)
    row = db.execute(select(ToolRegistry).where(ToolRegistry.tool_name == tool_name)).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"Tool {tool_name} was not found.")
    schema = dict(row.schema_json or {})
    schema["enabled"] = enabled
    row.schema_json = schema
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "tool_name": row.tool_name,
        "description": row.description,
        "permission_level": row.permission_level,
        "requires_confirmation": row.requires_confirmation,
        "enabled": enabled,
    }


def is_tool_enabled(db: Session, tool_name: str) -> bool:
    ensure_tool_registry(db)
    row = db.execute(select(ToolRegistry).where(ToolRegistry.tool_name == tool_name)).scalar_one_or_none()
    if row is None:
        return True
    return bool((row.schema_json or {}).get("enabled", True))


def _tool_names() -> list[str]:
    return [str(tool["tool_name"]) for tool in REGISTERED_TOOLS]
