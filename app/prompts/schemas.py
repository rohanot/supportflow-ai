from __future__ import annotations

from datetime import date as DateType

from pydantic import BaseModel, Field


class PromptVersion(BaseModel):
    version: str
    date: DateType | None = None
    change: str


class PromptDefinition(BaseModel):
    name: str
    version: str
    owner: str
    purpose: str
    inputs: list[str] = Field(default_factory=list)
    guardrails: list[str] = Field(default_factory=list)
    template: str
    change_log: list[PromptVersion] = Field(default_factory=list)


class PromptRegistryEntry(BaseModel):
    path: str
    active_version: str


class PromptRenderResult(BaseModel):
    prompt_name: str
    prompt_version: str
    prompt_hash: str
    rendered_prompt: str
    template_path: str
