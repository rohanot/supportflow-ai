from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.chat import router as chat_router
from app.api.v1.health import router as health_router
from app.api.v1.hitl import router as hitl_router
from app.api.v1.ops import router as ops_router
from app.api.v1.retrieval import router as retrieval_router
from app.api.v1.tools import router as tools_router

api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)
api_router.include_router(retrieval_router)
api_router.include_router(tools_router)
api_router.include_router(chat_router)
api_router.include_router(hitl_router)
api_router.include_router(ops_router)
