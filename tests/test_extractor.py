import json

import httpx
import pytest

from app.adapters import LocalExtractor
from app.config import Settings
from app.schemas import ProcessOptions, Segment


@pytest.mark.parametrize("evidence,valid", [("Сделать отчёт", True), ("invented", False)])
def test_extractor_validates_source(monkeypatch, evidence, valid):
    real_client = httpx.Client

    def handler(request):
        body = json.loads(request.content)
        assert body["stream"] is False
        assert body["format"]["type"] == "object"
        assert request.url.host == "127.0.0.1"
        return httpx.Response(200, json={"message": {"content": json.dumps({
            "summary": "Отчёт", "tasks": [{"description": "Сделать отчёт",
            "source_segment": 0, "evidence": evidence, "speaker_id": "invented",
            "responsible": None, "deadline_text": None, "deadline": None}]})}})

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: real_client(
        **kwargs, transport=httpx.MockTransport(handler)))
    extractor = LocalExtractor(Settings())
    segments = [Segment(start=0, end=1, text="Сделать отчёт", speaker_id="S0")]
    if valid:
        _, tasks = extractor.extract(segments, ProcessOptions())
        assert tasks[0].speaker_id == "S0"
        assert tasks[0].responsible is None
    else:
        summary, tasks = extractor.extract(segments, ProcessOptions())
        assert summary == "Отчёт"
        assert tasks[0].evidence_status == "unverified"
        assert tasks[0].evidence is None
        assert tasks[0].speaker_id is None
        assert tasks[0].proposed_evidence == "invented"


def test_evidence_repair_and_checkpoint(monkeypatch, tmp_path):
    from uuid import uuid4

    from app.pipeline import Pipeline

    real_client = httpx.Client
    calls = []

    def handler(request):
        calls.append(request)
        result = ({"summary": "Отчёт", "tasks": [{"description": "Сделать отчёт",
            "source_segment": 999, "evidence": "invented", "responsible": None,
            "deadline_text": None, "deadline": None}]} if len(calls) == 1 else
            {"source_segment": 0, "evidence": "Сделать отчёт"})
        return httpx.Response(200, json={"message": {"content": json.dumps(result)}})

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: real_client(
        **kwargs, transport=httpx.MockTransport(handler)))
    segments = [Segment(start=0, end=1, text="Сделать отчёт", speaker_id="S0")]
    settings = Settings(data_dir=tmp_path)
    _, tasks = LocalExtractor(settings).extract(segments, ProcessOptions())
    assert len(calls) == 2
    assert tasks[0].evidence_status == "verified"
    assert tasks[0].evidence == "Сделать отчёт"
    assert tasks[0].speaker_id == "S0"
    mid = uuid4()
    Pipeline(settings).save_transcript(mid, "stt", segments)
    path = tmp_path / "transcripts" / f"{mid}-stt.json"
    assert json.loads(path.read_text(encoding="utf-8"))[0]["text"] == "Сделать отчёт"
    assert not list((tmp_path / "transcripts").glob("*.tmp"))
