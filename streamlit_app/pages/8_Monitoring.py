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
    st.title("Monitoring")
    st.caption("Inspect trace-linked requests, retrieval events, prompt renders, graph nodes, and tool calls.")
    with st.expander("How to use this page", expanded=True):
        st.markdown(
            """
            - Paste a `trace_id` from Chat or Retrieval Debugger to inspect one request.
            - Leave it blank to see recent traces.
            - Use the tabs to isolate graph, retrieval, prompt, tool, and clarification evidence.
            """
        )
    trace_id = st.text_input("Trace ID")
    if requests is None:
        st.warning("The requests package is unavailable in this Streamlit runtime.")
        return
    if trace_id:
        response = requests.get(f"{API_BASE_URL}/api/v1/traces/{trace_id}", timeout=10)
        st.caption(f"Trace detail status: {response.status_code}")
        payload = response.json()
        if isinstance(payload, dict):
            tabs = st.tabs(["Summary", "Graph", "Retrieval", "Prompts", "Tools", "State"])
            tabs[0].json(payload.get("trace"))
            tabs[1].dataframe(payload.get("graph") or [], use_container_width=True)
            tabs[2].dataframe(payload.get("retrieval") or [], use_container_width=True)
            tabs[3].dataframe(payload.get("prompts") or [], use_container_width=True)
            tabs[4].dataframe(payload.get("tools") or [], use_container_width=True)
            tabs[5].dataframe(payload.get("state_transitions") or [], use_container_width=True)
        st.json(payload)
    else:
        response = requests.get(f"{API_BASE_URL}/api/v1/traces", timeout=10)
        st.caption(f"Recent traces status: {response.status_code}")
        st.dataframe(response.json(), use_container_width=True)


if __name__ == "__main__":
    render()
