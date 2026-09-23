"""Run from repository root: streamlit run app/ui.py"""
import httpx
import streamlit as st

API = "http://127.0.0.1:8000"
st.set_page_config(page_title="Meeting minutes", layout="wide")
st.title("Local meeting minutes")
st.info("Base project: uploads and manual task tracking work. AI processing and exports are planned.")
st.caption("Notify participants before recording. Use anonymized recordings for the demo.")


def request(method, path, **kwargs):
    try:
        with httpx.Client(base_url=API, timeout=120, trust_env=False) as client:
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        st.error(f"Backend request failed: {exc}")
        return None


file = st.file_uploader("Audio or video", type=["wav", "mp3", "m4a", "ogg", "flac", "mp4", "mov", "webm", "mkv"])
if st.button("Upload", disabled=file is None):
    result = request("POST", "/meetings", files={"file": (file.name, file.getvalue(), file.type)})
    if result:
        st.success("Saved locally")

meetings = request("GET", "/meetings")
if meetings:
    selected = st.selectbox("Meeting", meetings, format_func=lambda m: f"{m['filename']} ({m['id'][:8]})")
    with st.form("manual_task"):
        description = st.text_input("Task")
        responsible = st.text_input("Responsible person (leave blank if unknown)")
        has_deadline = st.checkbox("Deadline is known")
        deadline = st.date_input("Deadline")
        if st.form_submit_button("Add task for review") and description.strip():
            request("POST", f"/meetings/{selected['id']}/tasks", json={
                "description": description, "responsible": responsible or None,
                "deadline": deadline.isoformat() if has_deadline else None})

st.subheader("Task dashboard")
tasks = request("GET", "/tasks")
if tasks:
    status_filter = st.selectbox("Filter", ["all", "pending", "in_progress", "overdue", "completed"])
    shown = [t for t in tasks if status_filter == "all" or t["dashboard_status"] == status_filter]
    st.dataframe(shown, width="stretch")
    chosen = st.selectbox("Update task", tasks, format_func=lambda t: t["description"])
    status = st.selectbox("New status", ["pending", "in_progress", "completed"])
    if st.button("Save status") and request("PATCH", f"/tasks/{chosen['id']}", json={"status": status}):
        st.rerun()
