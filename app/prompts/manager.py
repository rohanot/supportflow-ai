from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy.orm import Session

from app.db.models import PromptEvent
from app.observability.redaction import redact_value
from app.prompts.renderer import hash_prompt, render_template
from app.prompts.schemas import PromptDefinition, PromptRegistryEntry, PromptRenderResult


@dataclass(frozen=True)
class PromptRecord:
    name: str
    entry: PromptRegistryEntry
    definition: PromptDefinition
    path: Path


class PromptManager:
    def __init__(self, prompts_root: Path | str = "prompts") -> None:
        self.prompts_root = Path(prompts_root)
        self.registry_path = self.prompts_root / "registry.yaml"
        self._registry = self._load_registry()

    def _load_registry(self) -> dict[str, PromptRegistryEntry]:
        data = yaml.safe_load(self.registry_path.read_text(encoding="utf-8")) or {}
        prompts = data.get("prompts", {})
        return {name: PromptRegistryEntry.model_validate(entry) for name, entry in prompts.items()}

    def list_prompts(self) -> list[str]:
        return sorted(self._registry)

    def load_prompt(self, name: str) -> PromptRecord:
        entry = self._registry[name]
        path = self.prompts_root / Path(entry.path).relative_to(self.prompts_root)
        definition = PromptDefinition.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        return PromptRecord(name=name, entry=entry, definition=definition, path=path)

    def render_prompt(
        self,
        name: str,
        *,
        db: Session | None = None,
        trace_id: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        **inputs: object,
    ) -> PromptRenderResult:
        record = self.load_prompt(name)
        render_inputs = {key: inputs.get(key) for key in record.definition.inputs}
        render_inputs.update(inputs)
        rendered = render_template(record.definition.template, **render_inputs)
        result = PromptRenderResult(
            prompt_name=record.definition.name,
            prompt_version=record.definition.version,
            prompt_hash=hash_prompt(rendered),
            rendered_prompt=rendered,
            template_path=str(record.path),
        )
        if db is not None and trace_id:
            db.add(
                PromptEvent(
                    trace_id=trace_id,
                    prompt_name=result.prompt_name,
                    prompt_version=result.prompt_version,
                    prompt_hash=result.prompt_hash,
                    prompt_inputs_redacted=redact_value(render_inputs),
                    rendered_prompt_preview=rendered[:500],
                    model=model,
                    provider=provider,
                )
            )
            db.flush()
        return result
