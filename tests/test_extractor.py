import json

import httpx
import pytest

from app.adapters import LocalExtractor, PipelineError
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
        with pytest.raises(PipelineError):
            extractor.extract(segments, ProcessOptions())
