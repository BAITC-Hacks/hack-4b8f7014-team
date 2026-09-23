from datetime import date, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class TaskStatus(StrEnum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"


class Segment(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str
    speaker_id: str | None = None

    @model_validator(mode="after")
    def valid_interval(self):
        if self.end < self.start:
            raise ValueError("Segment end precedes start")
        return self


class TaskCreate(BaseModel):
    description: str = Field(min_length=1, max_length=4000)
    responsible: str | None = Field(default=None, max_length=200)
    speaker_id: str | None = None
    deadline: date | None = None
    deadline_text: str | None = None
    evidence: str | None = None
    evidence_status: Literal["manual", "verified", "unverified"] = "manual"
    proposed_evidence: str | None = None
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


class TaskReview(TaskCreate):
    needs_review: bool = False


class ProcessOptions(BaseModel):
    language: Literal["auto", "ru", "kk", "mixed"] = "auto"
    meeting_date: date | None = None


class ReportPoint(BaseModel):
    direction: str
    indicator: str
    problem: str


class MinutesReview(BaseModel):
    summary: str = Field(max_length=50000)
    speakers: dict[str, str] = Field(default_factory=dict)
    organization: str | None = None
    topic: str | None = None
    report_points: list[ReportPoint] | None = None


class TranscriptReview(BaseModel):
    transcript: list[Segment] = Field(min_length=1)


class Meeting(BaseModel):
    id: UUID
    filename: str
    created_at: datetime
    status: str = "uploaded"
    stage: str | None = None
    error: str | None = None
    options: ProcessOptions = Field(default_factory=ProcessOptions)


class Minutes(BaseModel):
    meeting_id: UUID
    summary: str
    transcript: list[Segment]
    tasks: list[Task]
    # Explicit human mapping: diarization labels are not verified identities.
    speakers: dict[str, str] = Field(default_factory=dict)
    organization: str = ""
    topic: str = ""
    report_points: list[ReportPoint] = Field(default_factory=list)
