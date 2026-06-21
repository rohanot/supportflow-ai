from __future__ import annotations

import contextvars
import hashlib
import re
import uuid
from collections.abc import Callable, Awaitable

from fastapi import Request, Response

trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")
TRACE_ID_MAX_LENGTH = 64
TRACE_ID_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def new_trace_id() -> str:
    return uuid.uuid4().hex


def normalize_trace_id(trace_id: str | None) -> str:
    candidate = TRACE_ID_SAFE_RE.sub("_", str(trace_id or "").strip())
    if not candidate:
        return new_trace_id()
    if len(candidate) <= TRACE_ID_MAX_LENGTH:
        return candidate
    digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()[:16]
    prefix = candidate[: TRACE_ID_MAX_LENGTH - 17].rstrip("._-")
    if not prefix:
        return digest
    return f"{prefix}_{digest}"


def set_trace_id(trace_id: str) -> None:
    trace_id_var.set(normalize_trace_id(trace_id))


def get_trace_id() -> str:
    trace_id = trace_id_var.get()
    return trace_id or new_trace_id()


async def trace_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    header_name = request.app.state.settings.trace_header_name
    trace_id = normalize_trace_id(request.headers.get(header_name) or new_trace_id())
    set_trace_id(trace_id)
    request.state.trace_id = trace_id
    response = await call_next(request)
    response.headers[header_name] = trace_id
    return response
