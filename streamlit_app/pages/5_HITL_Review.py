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
    st.title("HITL Review")
    st.caption("Approve or reject write actions before they commit to the mock booking system.")
    with st.expander("How to use this page", expanded=True):
        st.markdown(
            """
            - Booking creation, reschedule, and cancellation proposals land here as pending HITL requests.
            - Review the proposed payload before approving.
            - Approval commits the write action through the backend tool adapter; rejection leaves it unexecuted.
            """
        )
    if requests is None:
        st.warning("The requests package is unavailable in this Streamlit runtime.")
        return

    response = requests.get(f"{API_BASE_URL}/api/v1/hitl/pending", timeout=10)
    st.caption(f"HITL status: {response.status_code}")
    rows = response.json() if response.status_code == 200 else []
    if not rows:
        st.success("No pending human-review actions.")
        return
    st.dataframe(rows, use_container_width=True)
    for row in rows:
        with st.expander(f"Request {row['id']} | {row.get('reason', '')}", expanded=False):
            st.caption(f"Trace: {row.get('trace_id')}")
            st.json(row.get("payload", {}))
            col_approve, col_reject = st.columns(2)
            with col_approve:
                if st.button("Approve and execute", key=f"approve-{row['id']}"):
                    result = requests.post(f"{API_BASE_URL}/api/v1/hitl/{row['id']}/approve", timeout=30)
                    _show_response("Approve", result)
            with col_reject:
                if st.button("Reject", key=f"reject-{row['id']}"):
                    result = requests.post(f"{API_BASE_URL}/api/v1/hitl/{row['id']}/reject", timeout=30)
                    _show_response("Reject", result)


def _show_response(label: str, response) -> None:
    st.caption(f"{label} status: {response.status_code}")
    try:
        st.json(response.json())
    except Exception:
        st.text(response.text)


if __name__ == "__main__":
    render()
