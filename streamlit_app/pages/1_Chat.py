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
    st.title("Chat")
    st.caption("Customer-facing assistant, structured tool smoke tests, and confirmation-gated booking flows.")
    with st.expander("How to use this page", expanded=True):
        st.markdown(
            """
            - Use **Customer chat** for retrieval-grounded answers, clarification, handoff, and citations.
            - Use **Service area** to prove ZIP/service eligibility is deterministic and not RAG-based.
            - Use **Create booking** and **Reschedule / cancel** to generate confirmation-gated HITL actions.
            - Approve or reject pending writes from the **HITL Review** page before they commit.
            """
        )
    if requests is None:
        st.warning("The requests package is unavailable in this Streamlit runtime.")
        return

    tab_chat, tab_service, tab_create, tab_patch = st.tabs(
        ["Customer chat", "Service area", "Create booking", "Reschedule / cancel"]
    )

    with tab_chat:
        session_id = st.text_input("Session ID", value="streamlit-session")
        message = st.text_area("Customer message", value="What does a water heater replacement cost?")
        if st.button("Send chat message"):
            response = requests.post(
                f"{API_BASE_URL}/api/v1/chat",
                json={"session_id": session_id, "message": message},
                headers={"X-Trace-Id": f"ui-chat-{uuid4().hex}"},
                timeout=30,
            )
            _show_response("Chat", response)

    with tab_service:
        zip_code = st.text_input("ZIP code", value="20147")
        service_type = st.selectbox("Service type", ["plumbing", "hvac", "electrical"], index=0)
        if st.button("Check service area"):
            response = requests.post(
                f"{API_BASE_URL}/api/v1/tools/service-area/check",
                json={"zip_code": zip_code, "service_type": service_type},
                headers={"X-Trace-Id": f"ui-service-area-{uuid4().hex}"},
                timeout=15,
            )
            _show_response("Service area", response)

    with tab_create:
        st.info("This submits a proposed write action. It should return awaiting_confirmation until approved.")
        customer_id = st.text_input("Customer ID", value="cust-ui-001")
        booking_service = st.selectbox("Booking service", ["hvac", "plumbing", "electrical"], index=0)
        job_type = st.text_input("Job type", value="tune-up")
        booking_zip = st.text_input("Booking ZIP", value="22030")
        preferred_date = st.text_input("Preferred date", value="2026-07-02")
        preferred_window = st.selectbox("Preferred window", ["morning", "afternoon", "evening"], index=0)
        notes = st.text_area("Notes", value="Streamlit operator smoke test")
        if st.button("Propose booking"):
            response = requests.post(
                f"{API_BASE_URL}/mock/bookings",
                json={
                    "customer_id": customer_id,
                    "service_type": booking_service,
                    "job_type": job_type,
                    "zip_code": booking_zip,
                    "preferred_date": preferred_date,
                    "preferred_window": preferred_window,
                    "notes": notes,
                    "channel": "streamlit",
                },
                headers={"X-Trace-Id": f"ui-booking-{uuid4().hex}"},
                timeout=20,
            )
            _show_response("Booking proposal", response)

    with tab_patch:
        booking_id = st.text_input("Booking ID", value="MHS-EXAMPLE")
        action = st.selectbox("Action", ["reschedule", "cancel"], index=0)
        patch_payload: dict[str, object] = {"action": action}
        if action == "reschedule":
            patch_payload["new_date"] = st.text_input("New date", value="2026-07-03")
            patch_payload["new_window"] = st.selectbox("New window", ["morning", "afternoon", "evening"], index=1)
        else:
            patch_payload["cancel_reason"] = st.text_input("Cancel reason", value="Customer requested cancellation")
        if st.button("Propose booking change"):
            response = requests.patch(
                f"{API_BASE_URL}/mock/bookings/{booking_id}",
                json=patch_payload,
                headers={"X-Trace-Id": f"ui-booking-patch-{uuid4().hex}"},
                timeout=20,
            )
            _show_response("Booking change proposal", response)


def _show_response(label: str, response) -> None:
    st.caption(f"{label} status: {response.status_code}")
    try:
        payload = response.json()
    except Exception:
        st.text(response.text)
        return
    if isinstance(payload, dict) and payload.get("trace_id"):
        st.code(payload["trace_id"], language="text")
    st.json(payload)


if __name__ == "__main__":
    render()
