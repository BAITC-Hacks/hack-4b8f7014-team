from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from app.config import Settings
from app.main import create_app


def test_dashboard_can_create_manual_task(tmp_path, monkeypatch):
    api = create_app(Settings(data_dir=tmp_path))
    with TestClient(api) as client:
        client.post("/meetings", files={"file": ("demo.wav", b"fixture")})
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: TestClient(api))
    ui = AppTest.from_file(
        str(Path(__file__).resolve().parents[1] / "app/ui.py"), default_timeout=30
    ).run()
    assert not ui.exception
    ui.text_input[0].set_value("Prepare meeting summary")
    ui.text_input[1].set_value("Reviewer")
    ui.button(key="add_task").click().run()
    assert not ui.exception
    with TestClient(api) as client:
        tasks = client.get("/tasks").json()
    assert tasks[0]["responsible"] == "Reviewer"
    assert tasks[0]["deadline"] is None
