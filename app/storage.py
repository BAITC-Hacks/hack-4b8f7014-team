import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import UUID

from app.schemas import (
    Meeting,
    Minutes,
    MinutesReview,
    ProcessOptions,
    Task,
    TaskReview,
    TaskStatus,
)


class Store:
    """Small single-host repository; replace with PostgreSQL for multiple workers."""

    def __init__(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = data_dir / "minutes.sqlite3"
        with closing(self.connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS meetings (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, meeting_id TEXT NOT NULL, payload TEXT NOT NULL,
                    FOREIGN KEY(meeting_id) REFERENCES meetings(id));
                CREATE TABLE IF NOT EXISTS minutes (
                    meeting_id TEXT PRIMARY KEY REFERENCES meetings(id), payload TEXT NOT NULL);
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA foreign_keys = ON")
        return db

    def add_meeting(self, meeting: Meeting):
        with closing(self.connect()) as db, db:
            db.execute("INSERT INTO meetings VALUES (?, ?)",
                       (str(meeting.id), meeting.model_dump_json()))

    def meetings(self):
        with closing(self.connect()) as db:
            return [Meeting.model_validate_json(row[0]) for row in
                    db.execute("SELECT payload FROM meetings ORDER BY rowid DESC")]

    def has_meeting(self, meeting_id: UUID):
        with closing(self.connect()) as db:
            return db.execute("SELECT 1 FROM meetings WHERE id = ?", (str(meeting_id),)).fetchone()

    def meeting(self, meeting_id: UUID):
        with closing(self.connect()) as db:
            row = db.execute("SELECT payload FROM meetings WHERE id = ?", (str(meeting_id),)).fetchone()
            return Meeting.model_validate_json(row[0]) if row else None

    @staticmethod
    def _save_meeting(db, meeting):
        db.execute("UPDATE meetings SET payload = ? WHERE id = ?",
                   (meeting.model_dump_json(), str(meeting.id)))

    def enqueue(self, meeting_id: UUID, options: ProcessOptions):
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM meetings WHERE id = ?", (str(meeting_id),)).fetchone()
            if not row:
                raise KeyError(meeting_id)
            meeting = Meeting.model_validate_json(row[0])
            if meeting.status not in {"uploaded", "failed"}:
                raise ValueError("Meeting is already queued, running or completed")
            meeting.status, meeting.stage, meeting.error = "queued", None, None
            meeting.options = options
            self._save_meeting(db, meeting)
            return meeting

    def claim(self):
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            for (payload,) in db.execute("SELECT payload FROM meetings ORDER BY rowid"):
                meeting = Meeting.model_validate_json(payload)
                if meeting.status == "queued":
                    meeting.status, meeting.stage = "running", "preflight"
                    self._save_meeting(db, meeting)
                    return meeting
        return None

    def recover(self):
        # Called only while holding the exclusive worker OS lock.
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT payload FROM meetings").fetchall()
            for (payload,) in rows:
                meeting = Meeting.model_validate_json(payload)
                if meeting.status == "running":
                    meeting.status, meeting.stage = "queued", "recovered"
                    self._save_meeting(db, meeting)

    def progress(self, meeting_id: UUID, stage: str, error: str | None = None):
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM meetings WHERE id = ?", (str(meeting_id),)).fetchone()
            meeting = Meeting.model_validate_json(row[0])
            meeting.stage = stage
            if error:
                meeting.status, meeting.error = "failed", error
            self._save_meeting(db, meeting)

    def complete(self, minutes: Minutes):
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM meetings WHERE id = ?",
                             (str(minutes.meeting_id),)).fetchone()
            meeting = Meeting.model_validate_json(row[0])
            if meeting.status != "running":
                raise ValueError("Meeting is not running")
            db.execute("INSERT INTO minutes VALUES (?, ?)",
                       (str(minutes.meeting_id), minutes.model_dump_json()))
            for task in minutes.tasks:
                db.execute("INSERT INTO tasks VALUES (?, ?, ?)",
                           (str(task.id), str(task.meeting_id), task.model_dump_json()))
            meeting.status, meeting.stage, meeting.error = "completed", "done", None
            self._save_meeting(db, meeting)

    def minutes(self, meeting_id: UUID):
        with closing(self.connect()) as db:
            row = db.execute("SELECT payload FROM minutes WHERE meeting_id = ?",
                             (str(meeting_id),)).fetchone()
            if not row:
                return None
            minutes = Minutes.model_validate_json(row[0])
            # Tasks have one source of truth, including edits and manually added tasks.
            minutes.tasks = [Task.model_validate_json(r[0]) for r in db.execute(
                "SELECT payload FROM tasks WHERE meeting_id = ? ORDER BY rowid", (str(meeting_id),))]
            return minutes

    def review_minutes(self, meeting_id: UUID, review: MinutesReview):
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM minutes WHERE meeting_id = ?",
                             (str(meeting_id),)).fetchone()
            if not row:
                return None
            minutes = Minutes.model_validate_json(row[0])
            known = {s.speaker_id for s in minutes.transcript if s.speaker_id}
            if not set(review.speakers) <= known:
                raise ValueError("Unknown speaker label")
            minutes.summary, minutes.speakers = review.summary, review.speakers
            for field in ("organization", "topic", "report_points"):
                value = getattr(review, field)
                if value is not None:
                    setattr(minutes, field, value)
            db.execute("UPDATE minutes SET payload = ? WHERE meeting_id = ?",
                       (minutes.model_dump_json(), str(meeting_id)))
        return self.minutes(meeting_id)

    def review_task(self, task_id: UUID, review: TaskReview):
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM tasks WHERE id = ?", (str(task_id),)).fetchone()
            if not row:
                return None
            task = Task.model_validate_json(row[0])
            task = Task(id=task.id, meeting_id=task.meeting_id, **review.model_dump())
            db.execute("UPDATE tasks SET payload = ? WHERE id = ?",
                       (task.model_dump_json(), str(task_id)))
            return task

    def review_transcript(self, meeting_id, segments):
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM minutes WHERE meeting_id = ?", (str(meeting_id),)).fetchone()
            if not row:
                return None
            minutes = Minutes.model_validate_json(row[0])
            minutes.transcript = segments
            db.execute("UPDATE minutes SET payload = ? WHERE meeting_id = ?",
                       (minutes.model_dump_json(), str(meeting_id)))
            rows = db.execute("SELECT payload FROM tasks WHERE meeting_id = ?", (str(meeting_id),)).fetchall()
            for (payload,) in rows:
                task = Task.model_validate_json(payload)
                task.needs_review = True
                if task.evidence:
                    matches = [s for s in segments if task.evidence in s.text]
                    if not matches:
                        task.proposed_evidence = task.evidence
                        task.evidence = None
                        task.evidence_status = "unverified"
                        task.speaker_id = None
                    else:
                        task.speaker_id = matches[0].speaker_id if len(matches) == 1 else None
                db.execute("UPDATE tasks SET payload = ? WHERE id = ?", (task.model_dump_json(), str(task.id)))
        return self.minutes(meeting_id)

    def add_task(self, task: Task):
        with closing(self.connect()) as db, db:
            db.execute("INSERT INTO tasks VALUES (?, ?, ?)",
                       (str(task.id), str(task.meeting_id), task.model_dump_json()))

    def tasks(self):
        with closing(self.connect()) as db:
            return [Task.model_validate_json(row[0]) for row in
                    db.execute("SELECT payload FROM tasks ORDER BY rowid DESC")]

    def update_status(self, task_id: UUID, status: TaskStatus):
        with closing(self.connect()) as db, db:
            row = db.execute("SELECT payload FROM tasks WHERE id = ?", (str(task_id),)).fetchone()
            if not row:
                return None
            task = Task.model_validate_json(row[0])
            task.status = status
            db.execute("UPDATE tasks SET payload = ? WHERE id = ?",
                       (task.model_dump_json(), str(task_id)))
            return task
