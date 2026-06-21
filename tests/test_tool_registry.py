from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.tools.registry import list_registered_tools


def test_tool_registry_lists_registered_tools() -> None:
    tools = list_registered_tools()
    names = {tool["tool_name"] for tool in tools}

    assert {"check_service_area", "create_booking", "lookup_booking", "reschedule_booking", "cancel_booking"} <= names
    create_tool = next(tool for tool in tools if tool["tool_name"] == "create_booking")
    assert create_tool["requires_confirmation"] is True


def test_tool_registry_endpoint_lists_tools() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/tools")

    assert response.status_code == 200, response.text
    names = {tool["tool_name"] for tool in response.json()}
    assert "check_service_area" in names
    assert "create_booking" in names

