import queue
import threading
import wave
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.live import LiveRecorder
from app.main import create_app
from app.schemas import ProcessOptions, Segment
from app.storage import Store


def test_live_rejects_external_origin_and_invalid_device(tmp_path, monkeypatch):
    monkeypatch.setattr("app.live.devices", lambda: [{"index": 2, "name": "Test output"}])
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        assert client.get("/live").json() == {"status": "idle"}
        assert client.get("/live/devices").json()[0]["index"] == 2
        assert client.post("/live/start", json={"device_index": 2},
                           headers={"origin": "https://foreign.example"}).status_code == 403
        assert client.post("/live/start", json={"device_index": 99}).status_code == 409
        assert client.post("/live/stop").status_code == 202


def test_live_chunk_is_valid_and_offsets_are_preserved(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path)
    recorder = LiveRecorder(settings, Store(tmp_path))
    directory = tmp_path / "live" / "test"
    directory.mkdir(parents=True)
    recorder.state = {"id": "test", "warnings": []}
    pending = queue.Queue()
    recorder._chunk(pending, directory, b"\0\0" * 1600, 20, 1, 16000)
    path, offset = pending.get()
    with wave.open(str(path)) as audio:
        assert audio.getnframes() == 1600
        assert audio.getframerate() == 16000
    monkeypatch.setattr("app.live.normalize", lambda path, destination, settings: path)
    monkeypatch.setattr("app.live.LocalSTT.transcribe", lambda *a:
                        [Segment(start=0.1, end=0.2, text="Тест")])
    pending.put((path, offset))
    pending.put(None)
    recorder._analyse(pending, ProcessOptions())
    assert recorder.snapshot()["transcript"][0]["start"] == 20.1
    assert (directory / "session.json").is_file()


def test_capture_stops_without_audio_and_does_not_enqueue(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    entered = threading.Event()

    class Stream:
        def __enter__(self):
            entered.set()
            return self

        def __exit__(self, *args):
            pass

    class Audio(Stream):
        def __enter__(self):
            return self

        def get_device_info_by_index(self, index):
            return {"defaultSampleRate": 16000, "maxInputChannels": 1, "name": "Silent"}

        def open(self, **kwargs):
            return Stream()

    monkeypatch.setitem(sys.modules, "pyaudiowpatch", SimpleNamespace(PyAudio=Audio, paInt16=8,
                                                                    paContinue=0))
    monkeypatch.setattr("app.live.devices", lambda: [{"index": 0}])
    store = Store(tmp_path)
    recorder = LiveRecorder(Settings(data_dir=tmp_path), store)
    recorder.start(0, ProcessOptions())
    assert entered.wait(2)
    recorder.stop()
    recorder.thread.join(3)
    assert not recorder.thread.is_alive()
    assert recorder.snapshot()["status"] == "failed"
    assert not store.meetings()
    assert len(list(Path(tmp_path).glob("uploads/*.wav"))) == 1
