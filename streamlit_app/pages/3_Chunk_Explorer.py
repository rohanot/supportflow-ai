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
    st.title("Chunk Explorer")
    st.caption("Inspect the chunks that power retrieval, citations, and traceability.")
    with st.expander("How to use this page", expanded=True):
        st.markdown(
            """
            - Load recent chunks after upload/reindex to confirm ingestion worked.
            - Filter locally by `doc_type`, branch, or service to spot metadata extraction issues.
            - Use snippets to verify pricing rows, FAQ chunks, policy chunks, and branch-hours chunks are readable.
            """
        )
    limit = st.slider("Chunks to load", min_value=5, max_value=100, value=50)
    if requests is None:
        st.warning("The requests package is unavailable in this Streamlit runtime.")
        return

    response = requests.get(f"{API_BASE_URL}/api/v1/chunks", params={"limit": limit}, timeout=10)
    st.caption(f"Chunks status: {response.status_code}")
    chunks = response.json() if response.status_code == 200 else []
    doc_types = sorted({chunk.get("doc_type") for chunk in chunks if chunk.get("doc_type")})
    selected_doc_type = st.selectbox("Filter doc_type", ["All", *doc_types])
    search = st.text_input("Snippet contains", value="")
    filtered = chunks
    if selected_doc_type != "All":
        filtered = [chunk for chunk in filtered if chunk.get("doc_type") == selected_doc_type]
    if search:
        filtered = [chunk for chunk in filtered if search.lower() in str(chunk.get("snippet", "")).lower()]
    st.dataframe(filtered, use_container_width=True)


if __name__ == "__main__":
    render()
