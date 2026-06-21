try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

import os
from uuid import uuid4


API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


def render() -> None:
    if st is None:
        return
    st.title("Retrieval Debugger")
    st.caption("Run hybrid retrieval with citations, fused scores, confidence, and trace IDs.")
    with st.expander("How to use this page", expanded=True):
        st.markdown(
            """
            - Try exact-fact queries like `no-show fee`, `Herndon Saturday hours`, or `panel upgrade 100A to 200A`.
            - Optional filters narrow retrieval by document type or service type.
            - `eval_data` and `test_data` are excluded by default in the backend.
            """
        )
    query = st.text_input("Query", value="40 gallon water heater replacement price")
    doc_type = st.text_input("Optional doc_type filter", value="")
    service_type = st.text_input("Optional service_type filter", value="")
    top_k = st.slider("Final top-k", min_value=1, max_value=10, value=5)
    if st.button("Run retrieval") and requests is not None:
        filters = {}
        if doc_type:
            filters["doc_type"] = doc_type
        if service_type:
            filters["service_type"] = service_type
        response = requests.post(
            f"{API_BASE_URL}/api/v1/retrieval/test",
            json={"query": query, "filters": filters, "top_k": top_k, "include_debug": True},
            headers={"X-Trace-Id": f"ui-retrieval-{uuid4().hex}"},
            timeout=30,
        )
        st.caption(f"Retrieval status: {response.status_code}")
        payload = response.json()
        if isinstance(payload, dict):
            st.metric("Confidence", payload.get("confidence", 0.0))
            if payload.get("trace_id"):
                st.code(payload["trace_id"], language="text")
            if payload.get("citations"):
                st.subheader("Citations")
                st.dataframe(payload["citations"], use_container_width=True)
            if payload.get("fused_results"):
                st.subheader("Fused results")
                st.dataframe(payload["fused_results"], use_container_width=True)
        st.json(payload)


if __name__ == "__main__":
    render()
