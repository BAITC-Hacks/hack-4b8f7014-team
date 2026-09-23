"""Test real local STT + LLM without claiming diarization coverage."""
import json
from datetime import date
from pathlib import Path

from app.adapters import LocalExtractor, LocalSTT, align_speakers, normalize
from app.config import Settings
from app.schemas import ProcessOptions

settings = Settings()
options = ProcessOptions(language="ru", meeting_date=date(2026, 9, 23))
wav = normalize(Path("data/synthetic-meeting.wav"), Path("data/test-normalized.wav"), settings)
segments = LocalSTT(settings).transcribe(wav, options)
Path("data/stt-smoke.json").write_text(
    json.dumps([s.model_dump() for s in segments], ensure_ascii=False), encoding="utf-8")
# No speaker model in this partial test: unknown labels stay unknown.
segments = align_speakers(segments, [])
summary, tasks = LocalExtractor(settings).extract(segments, options)
result = {"scope": "real STT and LLM; diarization NOT tested", "summary": summary,
          "tasks": [t.model_dump(mode="json") for t in tasks]}
Path("data/llm-smoke.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
