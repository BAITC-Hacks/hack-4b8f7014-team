"""Contracts for the next milestone. No fake transcript or cloud fallback."""
from pathlib import Path
from typing import Protocol

from app.schemas import Minutes, Segment, TaskCreate


class SpeechToText(Protocol):
    def transcribe(self, wav: Path) -> list[Segment]: ...


class Diarizer(Protocol):
    def attribute(self, wav: Path, segments: list[Segment]) -> list[Segment]: ...


class Extractor(Protocol):
    def extract(self, segments: list[Segment]) -> tuple[str, list[TaskCreate]]: ...


class Exporter(Protocol):
    def export(self, minutes: Minutes, destination: Path) -> Path: ...


class Pipeline:
    """Future worker owns decoding, model loading, progress, retries and persistence."""

    def run(self, media: Path) -> Minutes:
        raise NotImplementedError("Wire local adapters and persistent jobs before enabling processing")
