import json
from pathlib import Path

from app.adapters import (
    LocalDiarizer,
    LocalExtractor,
    LocalSTT,
    PipelineError,
    normalize,
    readiness,
)
from app.schemas import Minutes, Task


class Pipeline:
    def __init__(self, settings, stt=None, diarizer=None, extractor=None):
        self.settings = settings
        self.stt = stt or LocalSTT(settings)
        self.diarizer = diarizer or LocalDiarizer(settings)
        self.extractor = extractor or LocalExtractor(settings)

    def run(self, meeting, progress):
        missing = [key for key, ok in readiness(self.settings).items()
                   if not ok and key != "pdf_font"]
        if missing:
            raise PipelineError("Не готовы локальные компоненты: " + ", ".join(missing))
        media = self.settings.data_dir / "uploads" / (
            str(meeting.id) + Path(meeting.filename).suffix.lower())
        wav = self.settings.data_dir / "audio" / f"{meeting.id}.wav"
        progress("decoding")
        normalize(media, wav, self.settings)
        progress("transcribing")
        segments = self.stt.transcribe(wav, meeting.options)
        self.save_transcript(meeting.id, "stt", segments)
        progress("diarizing")
        segments = self.diarizer.attribute(wav, segments)
        self.save_transcript(meeting.id, "diarized", segments)
        progress("extracting")
        summary, drafts = self.extractor.extract(segments, meeting.options)
        return Minutes(meeting_id=meeting.id, summary=summary, transcript=segments,
                       tasks=[Task(meeting_id=meeting.id, **draft.model_dump()) for draft in drafts])

    def save_transcript(self, meeting_id, stage, segments):
        directory = self.settings.data_dir / "transcripts"
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / f"{meeting_id}-{stage}.json"
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(json.dumps([s.model_dump() for s in segments],
                                        ensure_ascii=False), encoding="utf-8")
        temporary.replace(destination)
