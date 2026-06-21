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
    st.title("Prompt Audit")
    st.caption("Prompt registry visibility for context-engineering review and traceability.")
    with st.expander("How to use this page", expanded=True):
        st.markdown(
            """
            - Prompts are intentionally read-only in the UI so changes remain Git-auditable.
            - Review active versions, owners, purposes, and file paths before running evals.
            - Prompt render events are trace-linked from the Monitoring page.
            """
        )
    if requests is None:
        st.warning("The requests package is unavailable in this Streamlit runtime.")
        return

    response = requests.get(f"{API_BASE_URL}/api/v1/prompts", timeout=10)
    st.caption(f"Prompt audit status: {response.status_code}")
    prompts = response.json() if response.status_code == 200 else []
    st.dataframe(prompts, use_container_width=True)
    if prompts:
        prompt_names = [prompt["name"] for prompt in prompts]
        selected = st.selectbox("Inspect prompt registry row", prompt_names)
        st.json(next(prompt for prompt in prompts if prompt["name"] == selected))


if __name__ == "__main__":
    render()
