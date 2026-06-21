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
    st.title("Evals")
    st.caption("Run the V1 scenario harness and review persisted eval summaries.")
    with st.expander("How to use this page", expanded=True):
        st.markdown(
            """
            - Click **Run scenario evals** for a small end-to-end harness covering clarification, retrieval, HITL, and guardrails.
            - The backend writes `eval_results.md` and stores a row in `eval_runs`.
            - For CI, use `python -m pytest -q`; this UI button is for reviewer-facing smoke validation.
            """
        )
    if requests is None:
        st.warning("The requests package is unavailable in this Streamlit runtime.")
        return

    st.warning("This may call the backend chat/retrieval paths. Use sparingly when free-tier LLM keys are configured.")
    if st.button("Run scenario evals"):
        response = requests.post(f"{API_BASE_URL}/api/v1/evals/run", timeout=240)
        st.caption(f"Eval run status: {response.status_code}")
        try:
            st.json(response.json())
        except Exception:
            st.text(response.text)

    response = requests.get(f"{API_BASE_URL}/api/v1/evals", timeout=10)
    st.caption(f"Eval runs status: {response.status_code}")
    runs = response.json() if response.status_code == 200 else []
    st.dataframe(runs, use_container_width=True)
    if runs:
        latest = runs[0]
        col1, col2, col3 = st.columns(3)
        col1.metric("Total", latest.get("total_cases") or 0)
        col2.metric("Passed", latest.get("passed_cases") or 0)
        col3.metric("Failed", latest.get("failed_cases") or 0)
        st.json(latest.get("metrics") or {})


if __name__ == "__main__":
    render()
