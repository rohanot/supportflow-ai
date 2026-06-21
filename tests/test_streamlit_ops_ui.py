from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


REQUIRED_PAGES = [
    "1_Chat.py",
    "2_Knowledge_Upload.py",
    "3_Chunk_Explorer.py",
    "4_Retrieval_Debugger.py",
    "5_HITL_Review.py",
    "6_Tool_Registry.py",
    "7_Evals.py",
    "8_Monitoring.py",
    "9_Prompt_Audit.py",
    "10_Conversation_State.py",
]


def test_required_streamlit_pages_exist() -> None:
    pages_dir = Path("streamlit_app/pages")
    missing = [page for page in REQUIRED_PAGES if not (pages_dir / page).exists()]
    assert missing == []


def test_streamlit_pages_are_backend_clients_not_business_logic() -> None:
    pages_dir = Path("streamlit_app/pages")
    for page in REQUIRED_PAGES:
        source = (pages_dir / page).read_text(encoding="utf-8")
        assert "API_BASE_URL" in source
        assert "sqlalchemy" not in source.lower()
        assert "Session(" not in source


def test_ops_endpoints_support_streamlit_pages() -> None:
    client = TestClient(create_app())
    endpoints = [
        "/api/v1/documents",
        "/api/v1/chunks?limit=3",
        "/api/v1/prompts",
        "/api/v1/traces",
        "/api/v1/hitl/pending",
        "/api/v1/tools",
        "/api/v1/conversation-state",
        "/api/v1/evals",
    ]
    for endpoint in endpoints:
        response = client.get(endpoint)
        assert response.status_code == 200, (endpoint, response.text)


def test_operator_pages_expose_real_actions() -> None:
    pages_dir = Path("streamlit_app/pages")
    expectations = {
        "1_Chat.py": ["/api/v1/chat", "/mock/bookings", "/api/v1/tools/service-area/check"],
        "2_Knowledge_Upload.py": ["/api/v1/documents/upload", "/api/v1/documents/seed", "Delete selected document"],
        "5_HITL_Review.py": ["/api/v1/hitl/", "Approve and execute", "Reject"],
        "6_Tool_Registry.py": ["/api/v1/tools/", "Save tool setting"],
        "7_Evals.py": ["/api/v1/evals/run", "Run scenario evals"],
        "10_Conversation_State.py": ["What is conversation state", "awaiting confirmation"],
    }
    for page, snippets in expectations.items():
        source = (pages_dir / page).read_text(encoding="utf-8")
        for snippet in snippets:
            assert snippet in source, (page, snippet)
