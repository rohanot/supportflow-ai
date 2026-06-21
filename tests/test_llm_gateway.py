from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.errors import ConfigurationError
from app.db.models import LLMCall
from app.llm.gateway import call_structured, call_text, resolve_llm_model_spec
from app.llm.schemas import ClarificationQuestionResult


class FakeLiteLLM:
    def __init__(self, content: str) -> None:
        self.content = content
        self.last_kwargs: dict[str, object] = {}

    def completion(self, **kwargs: object) -> object:
        self.last_kwargs = dict(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=6),
        )


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        return None

    def commit(self) -> None:
        return None

    def close(self) -> None:
        return None


def test_resolve_llm_model_spec_prefixes_model() -> None:
    provider, model = resolve_llm_model_spec(provider="groq", model="llama-3.1-8b-instant")

    assert provider == "groq"
    assert model == "groq/llama-3.1-8b-instant"


def test_call_structured_uses_litellm_and_persists_call(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeLiteLLM('{"clarification_question":"Which service or item do you need a price for?"}')
    monkeypatch.setattr("app.llm.gateway.get_settings", lambda: SimpleNamespace(
        llm_provider="groq",
        llm_model="llama-3.1-8b-instant",
        llm_temperature=0.0,
        llm_max_tokens=128,
        llm_timeout_seconds=12.0,
        llm_max_retries=0,
        allow_fallback_llm=False,
    ))
    monkeypatch.setattr("app.llm.gateway._import_litellm", lambda: fake)

    session = FakeSession()
    try:
        result = call_structured(
            session,
            trace_id="trace-llm-structured",
            prompt_name="ask_clarification",
            prompt_inputs={
                "intent": "pricing",
                "missing_fields": ["item_or_service_requested"],
                "conversation_state": {},
                "user_message": "Give me the price?",
            },
            response_model=ClarificationQuestionResult,
        )

        llm_call = next(item for item in session.added if isinstance(item, LLMCall))

        assert result.clarification_question == "Which service or item do you need a price for?"
        assert fake.last_kwargs["model"] == "groq/llama-3.1-8b-instant"
        assert fake.last_kwargs["response_format"] == {"type": "json_object"}
        assert llm_call.provider == "groq"
        assert llm_call.model == "groq/llama-3.1-8b-instant"
        assert llm_call.status == "success"
    finally:
        session.close()


def test_call_text_uses_litellm(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeLiteLLM("The answer is grounded.")
    monkeypatch.setattr("app.llm.gateway.get_settings", lambda: SimpleNamespace(
        llm_provider="openrouter",
        llm_model="openai/gpt-4o-mini",
        llm_temperature=0.0,
        llm_max_tokens=64,
        llm_timeout_seconds=12.0,
        llm_max_retries=0,
        allow_fallback_llm=False,
    ))
    monkeypatch.setattr("app.llm.gateway._import_litellm", lambda: fake)

    session = FakeSession()
    try:
        text = call_text(
            session,
            trace_id="trace-llm-text",
            prompt_name="assistant_system",
            prompt_inputs={"user_message": "Hello", "conversation_state": {}, "retrieved_context": ""},
        )

        assert text == "The answer is grounded."
        assert fake.last_kwargs["model"] == "openrouter/gpt-4o-mini"
        assert fake.last_kwargs["temperature"] == 0.0
    finally:
        session.close()


def test_call_structured_raises_when_litellm_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.llm.gateway.get_settings", lambda: SimpleNamespace(
        llm_provider="groq",
        llm_model="llama-3.1-8b-instant",
        llm_temperature=0.0,
        llm_max_tokens=128,
        llm_timeout_seconds=12.0,
        llm_max_retries=0,
        allow_fallback_llm=False,
    ))
    monkeypatch.setattr(
        "app.llm.gateway._import_litellm",
        lambda: (_ for _ in ()).throw(ConfigurationError("LiteLLM is not installed in this runtime. Add litellm to the API image.")),
    )

    session = FakeSession()
    try:
        with pytest.raises(ConfigurationError, match="LiteLLM is not installed"):
            call_structured(
                session,
                trace_id="trace-llm-missing",
                prompt_name="ask_clarification",
                prompt_inputs={
                    "intent": "pricing",
                    "missing_fields": ["item_or_service_requested"],
                    "conversation_state": {},
                    "user_message": "Give me the price?",
                },
                response_model=ClarificationQuestionResult,
            )
    finally:
        session.close()
