import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import FastAPI, File, HTTPException, Response, UploadFile

from app.adapters import PipelineError, readiness
from app.config import Settings
from app.exports import export_docx, export_pdf
from app.schemas import (
    Meeting,
    MinutesReview,
    ProcessOptions,
    Segment,
    Task,
    TaskCreate,
    TaskReview,
    TaskUpdate,
    TranscriptReview,
)
from app.storage import Store

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".mp4", ".mov", ".webm", ".mkv"}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    store = Store(settings.data_dir)
    uploads = settings.data_dir / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    api = FastAPI(title="Local meeting minutes", version="0.1.0")

    @api.get("/health")
    def health():
        return {"status": "ok", "local_assets": readiness(settings)}

    @api.get("/meetings", response_model=list[Meeting])
    def meetings():
        return store.meetings()

    @api.post("/meetings", response_model=Meeting, status_code=201)
    async def upload(file: Annotated[UploadFile, File()]):
        filename = (file.filename or "upload").replace("\\", "/").split("/")[-1]
        suffix = Path(filename).suffix.lower()
        target = None
        try:
            if suffix not in ALLOWED_EXTENSIONS:
                raise HTTPException(415, "Unsupported audio/video extension")
            meeting_id = uuid4()
            target = uploads / f"{meeting_id}{suffix}"
            size = 0
            with target.open("xb") as output:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > settings.max_upload_mb * 1024 * 1024:
                        raise HTTPException(413, "Upload exceeds configured limit")
                    output.write(chunk)
            if size == 0:
                raise HTTPException(400, "Empty upload")
            meeting = Meeting(id=meeting_id, filename=filename,
                              created_at=datetime.now(UTC))
            store.add_meeting(meeting)
            return meeting
        except BaseException:
            if target is not None:
                target.unlink(missing_ok=True)
            raise
        finally:
            await file.close()

    @api.post("/meetings/{meeting_id}/process", status_code=202)
    def process(meeting_id: UUID, options: ProcessOptions):
        try:
            return store.enqueue(meeting_id, options)
        except KeyError as exc:
            raise HTTPException(404, "Meeting not found") from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @api.get("/meetings/{meeting_id}/minutes")
    def minutes_detail(meeting_id: UUID):
        result = store.minutes(meeting_id)
        if result is None:
            raise HTTPException(404, "Minutes not available yet")
        return result

    @api.get("/meetings/{meeting_id}/transcript", response_model=list[Segment])
    def saved_transcript(meeting_id: UUID):
        if not store.has_meeting(meeting_id):
            raise HTTPException(404, "Meeting not found")
        minutes = store.minutes(meeting_id)
        if minutes:
            return minutes.transcript
        for stage in ("diarized", "stt"):
            path = settings.data_dir / "transcripts" / f"{meeting_id}-{stage}.json"
            if path.is_file():
                return [Segment.model_validate(s) for s in json.loads(path.read_text(encoding="utf-8"))]
        return []

    @api.put("/meetings/{meeting_id}/transcript")
    def review_transcript(meeting_id: UUID, review: TranscriptReview):
        result = store.review_transcript(meeting_id, review.transcript)
        if result is None:
            raise HTTPException(404, "Minutes not found")
        return result

    @api.put("/meetings/{meeting_id}/minutes")
    def review_minutes(meeting_id: UUID, review: MinutesReview):
        try:
            result = store.review_minutes(meeting_id, review)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if result is None:
            raise HTTPException(404, "Minutes not found")
        return result

    @api.get("/meetings/{meeting_id}/export/{format}")
    def export(meeting_id: UUID, format: str):
        if format not in {"pdf", "docx"}:
            raise HTTPException(422, "Choose pdf or docx")
        meeting, minutes = store.meeting(meeting_id), store.minutes(meeting_id)
        if minutes is None:
            raise HTTPException(404, "Minutes not found")
        try:
            body = (export_docx(meeting, minutes) if format == "docx"
                    else export_pdf(meeting, minutes, settings.pdf_font))
        except PipelineError as exc:
            raise HTTPException(503, str(exc)) from exc
        media = ("application/pdf" if format == "pdf"
                 else "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        return Response(body, media_type=media, headers={
            "Content-Disposition": f'attachment; filename="minutes-{meeting_id}.{format}"'})

    @api.put("/tasks/{task_id}", response_model=Task)
    def review_task(task_id: UUID, review: TaskReview):
        result = store.review_task(task_id, review)
        if result is None:
            raise HTTPException(404, "Task not found")
        return result

    @api.get("/tasks")
    def tasks():
        return [dict(task.model_dump(mode="json"),
                     dashboard_status=task.dashboard_status(datetime.now().astimezone().date()))
                for task in store.tasks()]

    @api.post("/meetings/{meeting_id}/tasks", response_model=Task, status_code=201)
    def add_task(meeting_id: UUID, draft: TaskCreate):
        if not store.has_meeting(meeting_id):
            raise HTTPException(404, "Meeting not found")
        task = Task(meeting_id=meeting_id, **draft.model_dump())
        store.add_task(task)
        return task

    @api.patch("/tasks/{task_id}", response_model=Task)
    def update_task(task_id: UUID, update: TaskUpdate):
        task = store.update_status(task_id, update.status)
        if task is None:
            raise HTTPException(404, "Task not found")
        return task

    return api
