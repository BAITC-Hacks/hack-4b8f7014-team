import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import UUID

from app.schemas import Meeting, Task, TaskStatus


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
