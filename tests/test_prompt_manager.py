from __future__ import annotations

from app.prompts.manager import PromptManager


def test_prompt_manager_loads_registry_and_renders() -> None:
    manager = PromptManager()
    names = manager.list_prompts()
    assert "grounded_answer" in names

    rendered = manager.render_prompt(
        "ask_clarification",
        intent="pricing",
        missing_fields=["item_or_service_requested"],
    )
    assert rendered.prompt_name == "ask_clarification"
    assert rendered.prompt_version == "v2"
    assert rendered.prompt_hash
    assert "clarification question" in rendered.rendered_prompt.lower()
