from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="local", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    database_url: str = Field(
        default="postgresql+psycopg://serviceflow:serviceflow@localhost:5432/serviceflow",
        alias="DATABASE_URL",
    )
    trace_header_name: str = Field(default="X-Trace-Id", alias="TRACE_HEADER_NAME")
    api_port: int = Field(default=8000, alias="API_PORT")
    streamlit_port: int = Field(default=8501, alias="STREAMLIT_PORT")
    litellm_port: int = Field(default=4000, alias="LITELLM_PORT")
    allow_fallback_embeddings: bool = Field(default=False, alias="ALLOW_FALLBACK_EMBEDDINGS")
    allow_fallback_llm: bool = Field(default=False, alias="ALLOW_FALLBACK_LLM")
    llm_provider: str = Field(default="groq", alias="LLM_PROVIDER")
    llm_model: str = Field(default="llama-3.1-8b-instant", alias="LLM_MODEL")
    llm_temperature: float = Field(default=0.0, alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=512, alias="LLM_MAX_TOKENS")
    llm_timeout_seconds: float = Field(default=30.0, alias="LLM_TIMEOUT_SECONDS")
    llm_max_retries: int = Field(default=0, alias="LLM_MAX_RETRIES")
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
