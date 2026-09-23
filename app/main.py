from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile

from app.config import Settings
from app.schemas import Meeting, Task, TaskCreate, TaskUpdate
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
        return {"status": "ok", "inference": "not_implemented"}

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

    @api.post("/meetings/{meeting_id}/process", status_code=501)
    def process(meeting_id: UUID):
        if not store.has_meeting(meeting_id):
            raise HTTPException(404, "Meeting not found")
        raise HTTPException(501, "Scaffold only: local inference pipeline is not wired yet")

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
