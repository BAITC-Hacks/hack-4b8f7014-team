"""Run from repository root: streamlit run app/ui.py"""
import httpx
import streamlit as st

API = "http://127.0.0.1:8000"
st.set_page_config(page_title="Meeting minutes", layout="wide")
st.title("Протоколы совещаний")
st.caption("Запись → транскрипт → поручения → протокол. Обработка на вашем компьютере.")
st.info("Перед записью уведомите участников. Результат ИИ нужно проверить перед использованием.")


def request(method, path, binary=False, **kwargs):
    try:
        with httpx.Client(base_url=API, timeout=120, trust_env=False) as client:
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.content if binary else response.json()
    except httpx.HTTPError as exc:
        st.error(f"Backend request failed: {exc}")
        return None


health = request("GET", "/health")
if health:
    missing = [key for key, ready in health["local_assets"].items() if not ready]
    if missing:
        st.warning("Требуется настройка локальных компонентов: " + ", ".join(missing))
    st.caption("Проверка файлов не подтверждает запуск Ollama и фонового обработчика.")

file = st.file_uploader("Аудио или видео", type=["wav", "mp3", "m4a", "ogg", "flac", "mp4", "mov", "webm", "mkv"])
if st.button("Upload", disabled=file is None):
    result = request("POST", "/meetings", files={"file": (file.name, file.getvalue(), file.type)})
    if result:
        st.success("Saved locally")

meetings = request("GET", "/meetings")
if meetings:
    selected = st.selectbox("Meeting", meetings, format_func=lambda m: f"{m['filename']} ({m['id'][:8]})")
    st.write("Состояние:", selected["status"], selected.get("stage") or "")
    if selected.get("error"):
        st.error(selected["error"])
    with st.form("process"):
        language = st.selectbox("Язык записи", ["auto", "ru", "kk", "mixed"])
        known_date = st.checkbox("Дата совещания известна")
        meeting_date = st.date_input("Дата совещания")
        if st.form_submit_button("Обработать запись", disabled=selected["status"] not in {"uploaded", "failed"}):
            if request("POST", f"/meetings/{selected['id']}/process", json={
                "language": language, "meeting_date": meeting_date.isoformat() if known_date else None}):
                st.rerun()
    if st.button("Обновить состояние"):
        st.rerun()
    if selected["status"] == "completed":
        minutes = request("GET", f"/meetings/{selected['id']}/minutes")
        if minutes:
            with st.form(f"minutes_{selected['id']}"):
                summary = st.text_area("Краткое содержание", minutes["summary"], height=180)
                labels = sorted({s["speaker_id"] for s in minutes["transcript"] if s["speaker_id"]})
                speakers = {label: st.text_input(f"Имя для {label}", minutes["speakers"].get(label, "")) for label in labels}
                if st.form_submit_button("Сохранить саммари и имена"):
                    request("PUT", f"/meetings/{selected['id']}/minutes", json={
                        "summary": summary, "speakers": {k: v for k, v in speakers.items() if v}})
            with st.expander("Транскрипт"):
                for segment in minutes["transcript"]:
                    name = minutes["speakers"].get(segment["speaker_id"], segment["speaker_id"] or "Неизвестный")
                    st.text(f"[{segment['start']:.1f}–{segment['end']:.1f}] {name}: {segment['text']}")
            for extension in ("docx", "pdf"):
                if st.button(f"Подготовить {extension.upper()}"):
                    content = request("GET", f"/meetings/{selected['id']}/export/{extension}", binary=True)
                    if content:
                        st.download_button("Скачать " + extension.upper(), content,
                                           file_name=f"minutes.{extension}", key=extension)
    with st.form("manual_task"):
        description = st.text_input("Task")
        responsible = st.text_input("Responsible person (leave blank if unknown)")
        has_deadline = st.checkbox("Deadline is known")
        deadline = st.date_input("Deadline")
        if st.form_submit_button("Add task for review", key="add_task") and description.strip():
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
    with st.form(f"review_{chosen['id']}"):
        description = st.text_area("Поручение", chosen["description"])
        responsible = st.text_input("Ответственный", chosen["responsible"] or "")
        deadline = st.text_input("Срок YYYY-MM-DD (пусто, если неизвестен)", chosen["deadline"] or "")
        st.caption("Основание: " + (chosen["evidence"] or "Добавлено вручную"))
        reviewed = st.checkbox("Поручение, ответственный и срок проверены", not chosen["needs_review"])
        if st.form_submit_button("Сохранить проверку"):
            payload = {k: v for k, v in chosen.items() if k not in {"id", "meeting_id", "dashboard_status"}}
            payload.update(description=description, responsible=responsible or None,
                           deadline=deadline or None, needs_review=not reviewed)
            if request("PUT", f"/tasks/{chosen['id']}", json=payload):
                st.rerun()
    status = st.selectbox("New status", ["pending", "in_progress", "completed"])
    if st.button("Save status") and request("PATCH", f"/tasks/{chosen['id']}", json={"status": status}):
        st.rerun()
