try:
    import streamlit as st
except Exception:  # pragma: no cover - Streamlit is available in Docker
    st = None

try:  # pragma: no cover - requests is available in Docker
    import requests
except Exception:
    requests = None

import os


def render() -> None:
    if st is None:
        return
    st.set_page_config(page_title="ServiceFlow AI", layout="wide")
    st.title("ServiceFlow AI")
    st.caption("Meridian Home Services assistant scaffold")
    api_base = os.environ.get("API_BASE_URL", "http://localhost:8000")
    if requests is not None:
        try:
            response = requests.get(f"{api_base}/api/health", timeout=5)
            payload = response.json()
            if payload.get("status") == "ok":
                st.success(f"Backend healthy at {api_base}")
                st.json(payload)
            else:
                st.error(f"Backend returned unexpected status from {api_base}")
                st.json(payload)
        except Exception as exc:  # pragma: no cover - runtime guard
            st.error(f"Backend health check failed: {exc}")
    else:
        st.info("Backend health check helper is unavailable in this environment.")
    st.info("Backend health and workflow pages will land in later phases.")


if __name__ == "__main__":
    render()
