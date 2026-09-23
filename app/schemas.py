from datetime import date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TaskStatus(StrEnum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"


class Segment(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str
    speaker_id: str | None = None


class TaskCreate(BaseModel):
    description: str = Field(min_length=1, max_length=4000)
    responsible: str | None = Field(default=None, max_length=200)
    speaker_id: str | None = None
    deadline: date | None = None
    deadline_text: str | None = None
    evidence: str | None = None
    urgency: str | None = None
    category: str | None = None
    status: TaskStatus = TaskStatus.pending


class Task(TaskCreate):
    id: UUID = Field(default_factory=uuid4)
    meeting_id: UUID
    needs_review: bool = True

    def dashboard_status(self, today: date) -> str:
        if self.status != TaskStatus.completed and self.deadline and self.deadline < today:
            return "overdue"
        return self.status.value


class TaskUpdate(BaseModel):
    status: TaskStatus


class Meeting(BaseModel):
    id: UUID
    filename: str
    created_at: datetime
    status: str = "uploaded"


class Minutes(BaseModel):
    meeting_id: UUID
    summary: str
    transcript: list[Segment]
    tasks: list[Task]
    # Explicit human mapping: diarization labels are not verified identities.
    speakers: dict[str, str] = Field(default_factory=dict)
