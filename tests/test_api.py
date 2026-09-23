from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app


def client_at(path):
    return TestClient(create_app(Settings(data_dir=path, max_upload_mb=1)))


def test_upload_persistence_and_tasks(tmp_path):
    with client_at(tmp_path) as client:
        uploaded = client.post("/meetings", files={"file": ("../../test.wav", b"fixture")})
        assert uploaded.status_code == 201
        meeting = uploaded.json()
        assert meeting["filename"] == "test.wav"
        assert len(list((tmp_path / "uploads").glob("*.wav"))) == 1
        response = client.post(f"/meetings/{meeting['id']}/tasks", json={
            "description": "Подготовить есеп", "deadline": "2000-01-01"})
        assert response.status_code == 201
        task = response.json()
        assert task["responsible"] is None
        assert client.get("/tasks").json()[0]["dashboard_status"] == "overdue"
        assert client.patch(f"/tasks/{task['id']}", json={"status": "completed"}).status_code == 200
        assert client.post(f"/meetings/{meeting['id']}/process", json={}).status_code == 202
        assert client.post(f"/meetings/{meeting['id']}/process", json={}).status_code == 409
    with client_at(tmp_path) as client:
        assert len(client.get("/meetings").json()) == 1
        assert client.get("/tasks").json()[0]["dashboard_status"] == "completed"


@pytest.mark.parametrize("name,body,status", [
    ("bad.exe", b"x", 415), ("empty.wav", b"", 400),
    ("large.mp4", b"x" * (1024 * 1024 + 1), 413),
], ids=["extension", "empty", "oversized"])
def test_invalid_upload_cleanup(tmp_path, name, body, status):
    with client_at(tmp_path) as client:
        assert client.post("/meetings", files={"file": (name, body)}).status_code == status
        assert client.get("/meetings").json() == []
        assert list((tmp_path / "uploads").iterdir()) == []


def test_missing_records_and_invalid_status(tmp_path):
    with client_at(tmp_path) as client:
        assert client.post(f"/meetings/{uuid4()}/tasks", json={"description": "x"}).status_code == 404
        assert client.patch(f"/tasks/{uuid4()}", json={"status": "completed"}).status_code == 404
        assert client.patch(f"/tasks/{uuid4()}", json={"status": "invented"}).status_code == 422


def test_external_llm_rejected():
    with pytest.raises(ValidationError):
        Settings(ollama_url="https://external.example.com")


def test_transcript_available_when_extraction_failed(tmp_path):
    from app.pipeline import Pipeline
    from app.schemas import Segment
    from app.storage import Store

    with client_at(tmp_path) as client:
        uploaded = client.post("/meetings", files={"file": ("meeting.wav", b"fixture")}).json()
        mid = uploaded["id"]
        Pipeline(Settings(data_dir=tmp_path)).save_transcript(
            mid, "diarized", [Segment(start=0, end=1, text="Сохранённый текст", speaker_id="S0")])
        Store(tmp_path).progress(mid, "failed", error="Test extraction failure")
        response = client.get(f"/meetings/{mid}/transcript")
        assert response.status_code == 200
        assert response.json()[0]["text"] == "Сохранённый текст"
