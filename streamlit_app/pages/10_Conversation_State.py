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
    st.title("Conversation Debug State")
    st.caption("Stateful memory for the current task, not long-term customer memory.")
    with st.expander("What is conversation state and why show it?", expanded=True):
        st.markdown(
            """
            Conversation state is the backend record that lets the assistant handle multi-turn work safely:
            pending intent, missing fields, clarification questions, canonical query, citations, handoff status,
            and whether a write action is awaiting confirmation. Showing it here makes the case-study behavior
            debuggable without guessing why the graph routed a message a certain way.
            """
        )
    if requests is None:
        st.warning("The requests package is unavailable in this Streamlit runtime.")
        return

    limit = st.slider("States to load", min_value=5, max_value=100, value=25)
    session_filter = st.text_input("Filter session ID contains", value="")
    response = requests.get(f"{API_BASE_URL}/api/v1/conversation-state", params={"limit": limit}, timeout=10)
    st.caption(f"Conversation state status: {response.status_code}")
    states = response.json() if response.status_code == 200 else []
    if session_filter:
        states = [row for row in states if session_filter.lower() in row.get("session_id", "").lower()]
    st.dataframe(states, use_container_width=True)
    if states:
        selected_session = st.selectbox("Inspect session", [row["session_id"] for row in states])
        st.json(next(row for row in states if row["session_id"] == selected_session))


if __name__ == "__main__":
    render()
