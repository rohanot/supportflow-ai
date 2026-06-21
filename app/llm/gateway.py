from __future__ import annotations

import importlib
import json
import logging
import time
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import ConfigurationError, LLMUnavailableError
from app.db.models import LLMCall
from app.prompts.manager import PromptManager

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def resolve_llm_model_spec(provider: str | None = None, model: str | None = None) -> tuple[str, str]:
    settings = get_settings()
    resolved_provider = (provider or settings.llm_provider or "groq").strip().lower()
    resolved_model = (model or settings.llm_model or "llama-3.1-8b-instant").strip()
    if "/" in resolved_model:
        provider_prefix, _, bare_model = resolved_model.partition("/")
        return provider_prefix, resolved_model if resolved_provider == provider_prefix else f"{resolved_provider}/{bare_model}"
    return resolved_provider, f"{resolved_provider}/{resolved_model}"


def call_text(
    db: Session,
    *,
    trace_id: str,
    prompt_name: str,
    prompt_inputs: dict[str, object],
    model: str | None = None,
    provider: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    response = _call_llm(
        db,
        trace_id=trace_id,
        prompt_name=prompt_name,
        prompt_inputs=prompt_inputs,
        model=model,
        provider=provider,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=False,
    )
    return response["content"]


def call_structured(
    db: Session,
    *,
    trace_id: str,
    prompt_name: str,
    prompt_inputs: dict[str, object],
    response_model: type[T],
    model: str | None = None,
    provider: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> T:
    response = _call_llm(
        db,
        trace_id=trace_id,
        prompt_name=prompt_name,
        prompt_inputs=prompt_inputs,
        model=model,
        provider=provider,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=True,
    )
    try:
        payload = _extract_json_object(response["content"])
        return response_model.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise LLMUnavailableError(f"{prompt_name} returned invalid structured output: {exc}") from exc


def _call_llm(
    db: Session,
    *,
    trace_id: str,
    prompt_name: str,
    prompt_inputs: dict[str, object],
    model: str | None,
    provider: str | None,
    temperature: float | None,
    max_tokens: int | None,
    json_mode: bool,
) -> dict[str, object]:
    settings = get_settings()
    resolved_provider, resolved_model = resolve_llm_model_spec(provider=provider, model=model)
    prompt_manager = PromptManager()
    prompt_model = resolved_model
    prompt_provider = resolved_provider
    system_prompt = None
    if prompt_name not in {"assistant_system", "safety_policy"}:
        system_prompt = prompt_manager.render_prompt(
            "assistant_system",
            db=db,
            trace_id=trace_id,
            model=prompt_model,
            provider=prompt_provider,
            **{},
        ).rendered_prompt
        safety_prompt = prompt_manager.render_prompt(
            "safety_policy",
            db=db,
            trace_id=trace_id,
            model=prompt_model,
            provider=prompt_provider,
            **{},
        ).rendered_prompt
        system_prompt = f"{system_prompt}\n\n{safety_prompt}"

    task_prompt = prompt_manager.render_prompt(
        prompt_name,
        db=db,
        trace_id=trace_id,
        model=prompt_model,
        provider=prompt_provider,
        **prompt_inputs,
    )
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": task_prompt.rendered_prompt})

    llm_module = _import_litellm()
    started_at = time.perf_counter()
    logger.info(
        "llm call started",
        extra={
            "trace_id": trace_id,
            "llm_provider": prompt_provider,
            "llm_model": prompt_model,
            "llm_temperature": temperature if temperature is not None else settings.llm_temperature,
            "llm_timeout_seconds": settings.llm_timeout_seconds,
            "llm_max_retries": settings.llm_max_retries,
            "allow_fallback_llm": settings.allow_fallback_llm,
        },
    )
    try:
        completion_kwargs: dict[str, Any] = {
            "model": prompt_model,
            "messages": messages,
            "temperature": settings.llm_temperature if temperature is None else temperature,
            "max_tokens": settings.llm_max_tokens if max_tokens is None else max_tokens,
            "num_retries": settings.llm_max_retries,
            "timeout": settings.llm_timeout_seconds,
        }
        if json_mode:
            completion_kwargs["response_format"] = {"type": "json_object"}
        response = llm_module.completion(**completion_kwargs)
        content = _response_content(response)
        usage = getattr(response, "usage", None)
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        _persist_llm_call(
            db,
            trace_id=trace_id,
            prompt_name=prompt_name,
            prompt_version=task_prompt.prompt_version,
            prompt_hash=task_prompt.prompt_hash,
            model=prompt_model,
            provider=prompt_provider,
            temperature=settings.llm_temperature if temperature is None else temperature,
            latency_ms=latency_ms,
            status="success",
            input_tokens=getattr(usage, "prompt_tokens", None) if usage is not None else None,
            output_tokens=getattr(usage, "completion_tokens", None) if usage is not None else None,
        )
        logger.info(
            "llm call completed",
            extra={
                "trace_id": trace_id,
                "llm_provider": prompt_provider,
                "llm_model": prompt_model,
                "llm_temperature": temperature if temperature is not None else settings.llm_temperature,
                "llm_timeout_seconds": settings.llm_timeout_seconds,
                "llm_max_retries": settings.llm_max_retries,
                "allow_fallback_llm": settings.allow_fallback_llm,
            },
        )
        return {
            "content": content,
            "prompt_version": task_prompt.prompt_version,
            "prompt_hash": task_prompt.prompt_hash,
        }
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        _persist_llm_call(
            db,
            trace_id=trace_id,
            prompt_name=prompt_name,
            prompt_version=task_prompt.prompt_version,
            prompt_hash=task_prompt.prompt_hash,
            model=prompt_model,
            provider=prompt_provider,
            temperature=settings.llm_temperature if temperature is None else temperature,
            latency_ms=latency_ms,
            status="error",
            error_message=str(exc),
        )
        logger.exception(
            "llm call failed",
            extra={
                "trace_id": trace_id,
                "llm_provider": prompt_provider,
                "llm_model": prompt_model,
                "llm_temperature": temperature if temperature is not None else settings.llm_temperature,
                "llm_timeout_seconds": settings.llm_timeout_seconds,
                "llm_max_retries": settings.llm_max_retries,
                "allow_fallback_llm": settings.allow_fallback_llm,
            },
        )
        raise LLMUnavailableError(f"LLM call failed for {prompt_name}: {exc}") from exc


def _persist_llm_call(
    db: Session,
    *,
    trace_id: str,
    prompt_name: str,
    prompt_version: str,
    prompt_hash: str,
    model: str,
    provider: str,
    temperature: float | None,
    latency_ms: int | None,
    status: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    estimated_cost: float | None = None,
    error_message: str | None = None,
) -> None:
    db.add(
        LLMCall(
            trace_id=trace_id,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            prompt_hash=prompt_hash,
            model=model,
            provider=provider,
            temperature=temperature,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=estimated_cost,
            latency_ms=latency_ms,
            status=status,
            error_message=error_message,
        )
    )
    db.flush()


def _extract_json_object(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            stripped = "\n".join(lines[1:-1]).strip()
    if not stripped.startswith("{"):
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    payload = json.loads(stripped)
    if not isinstance(payload, dict):
        raise json.JSONDecodeError("LLM response was not a JSON object", stripped, 0)
    return payload


def _response_content(response: Any) -> str:
    choices = getattr(response, "choices", None)
    if not choices:
        raise ConfigurationError("LLM response did not include any choices")
    message = choices[0].message
    content = getattr(message, "content", None)
    if not content:
        raise ConfigurationError("LLM response did not include message content")
    return str(content)


def _import_litellm() -> Any:
    try:
        return importlib.import_module("litellm")
    except Exception as exc:  # pragma: no cover - import guard
        settings = get_settings()
        if settings.allow_fallback_llm:
            raise ConfigurationError("LiteLLM is unavailable and fallback LLM is enabled, but no fallback backend exists.") from exc
        raise ConfigurationError("LiteLLM is not installed in this runtime. Add litellm to the API image.") from exc
