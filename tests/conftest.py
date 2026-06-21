from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(autouse=True)
def fake_litellm_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FailingLiteLLM:
        def completion(self, **_: object) -> object:
            raise RuntimeError("LiteLLM is disabled in tests")

    monkeypatch.setattr("app.llm.gateway._import_litellm", lambda: _FailingLiteLLM(), raising=True)


def make_client() -> TestClient:
    return TestClient(create_app())
