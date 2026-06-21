try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

import os


API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


def render() -> None:
    if st is None:
        return
    st.title("Tool Registry")
    st.caption("Enable or disable backend tool adapters. Write tools still require explicit confirmation.")
    with st.expander("How to use this page", expanded=True):
        st.markdown(
            """
            - Disable a tool to block execution from chat, API smoke tests, and HITL approval paths.
            - Re-enable it when you want the agentic flow available again.
            - This is V1 local configuration, not an enterprise RBAC system.
            """
        )
    if requests is None:
        st.warning("The requests package is unavailable in this Streamlit runtime.")
        return

    response = requests.get(f"{API_BASE_URL}/api/v1/tools", timeout=10)
    st.caption(f"Tool registry status: {response.status_code}")
    tools = response.json() if response.status_code == 200 else []
    st.dataframe(tools, use_container_width=True)
    for tool in tools:
        name = str(tool["tool_name"])
        with st.expander(f"{name} ({tool.get('permission_level')})", expanded=False):
            st.write(tool.get("description"))
            st.caption(f"Requires confirmation: {tool.get('requires_confirmation')}")
            enabled = st.checkbox("Enabled", value=bool(tool.get("enabled", True)), key=f"enabled-{name}")
            if st.button("Save tool setting", key=f"save-{name}"):
                result = requests.patch(f"{API_BASE_URL}/api/v1/tools/{name}", json={"enabled": enabled}, timeout=10)
                _show_response("Tool update", result)


def _show_response(label: str, response) -> None:
    st.caption(f"{label} status: {response.status_code}")
    try:
        st.json(response.json())
    except Exception:
        st.text(response.text)


if __name__ == "__main__":
    render()
