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
    st.title("Knowledge Upload")
    st.caption("Upload PDFs and trigger the backend ingestion pipeline: parse, chunk, embed, index, and store.")
    with st.expander("How to use this page", expanded=True):
        st.markdown(
            """
            - Upload a Meridian PDF to ingest it into Postgres + pgvector.
            - Use **Reingest seed PDFs** after changing local source PDFs in `sl_docs`.
            - Use **Reindex selected document** after editing or replacing a source file.
            - Use **Delete selected document** to remove a document, its chunks, and related structured rows.
            """
        )
    if requests is None:
        st.warning("The requests package is unavailable in this Streamlit runtime.")
        return

    uploaded_file = st.file_uploader("Upload knowledge PDF", type=["pdf"])
    col_upload, col_seed = st.columns(2)
    with col_upload:
        if st.button("Upload and ingest", disabled=uploaded_file is None):
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
            response = requests.post(f"{API_BASE_URL}/api/v1/documents/upload", files=files, timeout=120)
            _show_response("Upload", response)
    with col_seed:
        if st.button("Reingest seed PDFs"):
            response = requests.post(f"{API_BASE_URL}/api/v1/documents/seed", timeout=300)
            _show_response("Seed ingestion", response)

    response = requests.get(f"{API_BASE_URL}/api/v1/documents", timeout=10)
    st.caption(f"Documents status: {response.status_code}")
    documents = response.json() if response.status_code == 200 else []
    st.dataframe(documents, use_container_width=True)

    if documents:
        options = {f"{doc['id']} | {doc['source_doc']} | {doc['doc_type']}": doc["id"] for doc in documents}
        selected_label = st.selectbox("Selected document", list(options))
        selected_id = options[selected_label]
        col_reindex, col_delete = st.columns(2)
        with col_reindex:
            if st.button("Reindex selected document"):
                response = requests.post(f"{API_BASE_URL}/api/v1/documents/{selected_id}/reindex", timeout=180)
                _show_response("Reindex", response)
        with col_delete:
            confirm_delete = st.checkbox("I understand this deletes document chunks and structured rows")
            if st.button("Delete selected document", disabled=not confirm_delete):
                response = requests.delete(f"{API_BASE_URL}/api/v1/documents/{selected_id}", timeout=30)
                _show_response("Delete", response)


def _show_response(label: str, response) -> None:
    st.caption(f"{label} status: {response.status_code}")
    try:
        st.json(response.json())
    except Exception:
        st.text(response.text)


if __name__ == "__main__":
    render()
