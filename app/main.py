from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.v1.mock_booking import router as mock_booking_router
from app.api.v1.router import api_router
from app.config import get_settings
from app.core.errors import ConflictError, LLMUnavailableError, NotFoundError, ServiceFlowError
from app.core.logging import configure_logging
from app.core.tracing import trace_middleware


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="ServiceFlow AI", version="0.1.0")
    app.state.settings = settings
    app.middleware("http")(trace_middleware)
    app.include_router(api_router)
    app.include_router(mock_booking_router)

    @app.exception_handler(ServiceFlowError)
    async def serviceflow_error_handler(_, exc: ServiceFlowError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(NotFoundError)
    async def not_found_error_handler(_, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    async def conflict_error_handler(_, exc: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(LLMUnavailableError)
    async def llm_unavailable_error_handler(_, exc: LLMUnavailableError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

    return app


app = create_app()
