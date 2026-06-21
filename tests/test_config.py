from __future__ import annotations

from app.config import Settings


def test_settings_defaults() -> None:
    settings = Settings()
    assert settings.trace_header_name == "X-Trace-Id"
    assert settings.api_port == 8000
    assert settings.allow_fallback_llm is False
    assert settings.llm_provider == "groq"
