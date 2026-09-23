"""Windows desktop loopback recording with incremental, explicitly provisional minutes."""
import json
import queue
import threading
import time
import wave
from datetime import UTC, datetime
from uuid import uuid4

from app.adapters import LocalExtractor, LocalSTT, PipelineError, normalize
from app.schemas import Meeting, ProcessOptions


def devices():
    try:
        import pyaudiowpatch as pa
        with pa.PyAudio() as audio:
            return [{"index": int(d["index"]), "name": d["name"]}
                    for d in audio.get_loopback_device_info_generator()]
    except (ImportError, OSError) as exc:
        raise PipelineError("Захват системного звука требует Windows и requirements-live.txt") from exc


class LiveRecorder:
    def __init__(self, settings, store):
        self.settings, self.store = settings, store
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.state = {"status": "idle"}
        self.thread = None

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.state, ensure_ascii=False))

    def update(self, **fields):
        with self.lock:
            self.state.update(fields)
            if self.state.get("id"):
                path = self.settings.data_dir / "live" / self.state["id"] / "session.json"
                temp = path.with_suffix(".tmp")
                temp.write_text(json.dumps(self.state, ensure_ascii=False), encoding="utf-8")
                temp.replace(path)

    def start(self, device_index: int, options: ProcessOptions):
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise PipelineError("Предыдущая запись ещё обрабатывается")
            if any(m.status in {"queued", "running"} for m in self.store.meetings()):
                raise PipelineError("Дождитесь окончания обработки загруженных записей перед живым режимом")
            if device_index not in {d["index"] for d in devices()}:
                raise PipelineError("Выберите устройство системного звука из списка")
            mid = uuid4()
            directory = self.settings.data_dir / "live" / str(mid)
            directory.mkdir(parents=True)
            self.stop_event.clear()
            self.state = {"id": str(mid), "status": "starting", "seconds": 0,
                          "transcript": [], "summary": "", "tasks": [], "warnings": []}
            self.thread = threading.Thread(target=self._run,
                args=(mid, device_index, options, directory), daemon=True)
            self.thread.start()
            return self.snapshot()

    def stop(self):
        self.stop_event.set()
        return self.snapshot()

    def _run(self, mid, device_index, options, directory):
        chunks = queue.Queue()
        consumer = threading.Thread(target=self._analyse, args=(chunks, options), daemon=True)
        consumer.start()
        destination = self.settings.data_dir / "uploads" / f"{mid}.wav"
        destination.parent.mkdir(parents=True, exist_ok=True)
        frames_total = 0
        try:
            import pyaudiowpatch as pa
            with pa.PyAudio() as audio:
                device = audio.get_device_info_by_index(device_index)
                rate, channels = int(device["defaultSampleRate"]), int(device["maxInputChannels"])
                block = max(1, rate // 10)
                with wave.open(str(destination), "wb") as output:
                    output.setparams((channels, 2, rate, 0, "NONE", "not compressed"))
                    incoming = queue.Queue(maxsize=100)
                    overflow = threading.Event()

                    def callback(data, frame_count, time_info, status):
                        if status:
                            overflow.set()
                        try:
                            incoming.put_nowait(data)
                        except queue.Full:
                            overflow.set()
                        return None, pa.paContinue

                    with audio.open(format=pa.paInt16, channels=channels, rate=rate, input=True,
                                    input_device_index=device_index, frames_per_buffer=block,
                                    stream_callback=callback):
                        self.update(status="recording", device=device["name"])
                        buffer, start = bytearray(), 0.0
                        wall_start = time.monotonic()
                        while not self.stop_event.is_set():
                            if time.monotonic() - wall_start >= self.settings.max_audio_seconds:
                                break
                            if overflow.is_set():
                                raise PipelineError("Звуковой поток потерял данные. Сохранена запись до сбоя.")
                            try:
                                data = incoming.get(timeout=0.25)
                            except queue.Empty:
                                continue
                            output.writeframes(data)
                            frames_total += len(data) // (2 * channels)
                            buffer.extend(data)
                            seconds = frames_total / rate
                            self.update(seconds=round(seconds, 1), pending_chunks=chunks.qsize())
                            if seconds - start >= self.settings.live_chunk_seconds:
                                self._chunk(chunks, directory, buffer, start, channels, rate)
                                buffer, start = bytearray(), seconds
                            if (seconds >= self.settings.max_audio_seconds or
                                    frames_total * channels * 2 >= self.settings.max_upload_mb * 1024**2):
                                break
                        if buffer:
                            self._chunk(chunks, directory, buffer, start, channels, rate)
            self.update(status="finishing")
        except Exception as exc:
            self.update(status="finishing", capture_error=f"{type(exc).__name__}: {exc}")
        finally:
            chunks.put(None)
            consumer.join()
        if frames_total:
            try:
                meeting = Meeting(id=mid, filename="Живое совещание.wav", created_at=datetime.now(UTC))
                self.store.add_meeting(meeting)
                self.store.enqueue(mid, options)
                self.update(status="queued", meeting_id=str(mid))
            except Exception as exc:
                self.update(status="failed", error=f"Запись сохранена, ошибка очереди: {exc}")
        else:
            self.update(status="failed", error="Звук не записан. Проверьте выбранное устройство.")

    @staticmethod
    def _chunk(chunks, directory, buffer, start, channels, rate):
        path = directory / f"chunk-{start:.3f}.wav"
        with wave.open(str(path), "wb") as output:
            output.setparams((channels, 2, rate, 0, "NONE", "not compressed"))
            output.writeframes(buffer)
        chunks.put((path, start))

    def _analyse(self, chunks, options):
        # CPU preview leaves GPU free and never substitutes for final large-model processing.
        preview = self.settings.model_copy(update={"stt_model_dir": self.settings.live_stt_model_dir,
            "stt_device": "cpu", "stt_compute_type": "int8", "device": "cpu"})
        stt = LocalSTT(preview)
        transcript, last_summary = [], 0.0
        while (item := chunks.get()) is not None:
            path, offset = item
            try:
                wav = normalize(path, path.with_name(path.stem + "-mono.wav"), preview)
                found = stt.transcribe(wav, options)
                for segment in found:
                    segment.start += offset
                    segment.end += offset
                transcript.extend(found)
                self.update(transcript=[s.model_dump() for s in transcript],
                            transcribed_seconds=round(found[-1].end, 1))
                # Do not delay catch-up or stopping for another provisional LLM pass.
                if (found[-1].end - last_summary >= 60 and chunks.empty()
                        and not self.stop_event.is_set()):
                    extractor = LocalExtractor(preview)
                    summary, tasks = extractor.extract(transcript[-400:], options)
                    self.update(summary=summary,
                                tasks=[t.model_dump(mode="json") for t in tasks])
                    last_summary = found[-1].end
            except Exception as exc:
                warning = str(exc) if isinstance(exc, PipelineError) else type(exc).__name__
                with self.lock:
                    warnings = self.state["warnings"][-9:] + [f"{offset:.0f} с: {warning}"]
                self.update(warnings=warnings)


def register_live(api, settings, store):
    from fastapi import HTTPException, Request
    from pydantic import BaseModel, Field

    class Start(BaseModel):
        device_index: int = Field(ge=0)
        options: ProcessOptions = Field(default_factory=ProcessOptions)

    recorder = LiveRecorder(settings, store)
    api.state.live_recorder = recorder

    def local_request(request):
        if request.client and request.client.host not in {"127.0.0.1", "::1", "testclient"}:
            raise HTTPException(403, "Запись доступна только с этого компьютера")
        origin = request.headers.get("origin")
        if origin and origin not in {"http://127.0.0.1:8501", "http://localhost:8501"}:
            raise HTTPException(403, "Недопустимый источник запроса")

    @api.get("/live/devices")
    def live_devices(request: Request):
        local_request(request)
        try:
            return devices()
        except PipelineError as exc:
            raise HTTPException(503, str(exc)) from exc

    @api.get("/live")
    def live_status(request: Request):
        local_request(request)
        return recorder.snapshot()

    @api.post("/live/start", status_code=202)
    def live_start(payload: Start, request: Request):
        local_request(request)
        try:
            return recorder.start(payload.device_index, payload.options)
        except PipelineError as exc:
            raise HTTPException(409, str(exc)) from exc

    @api.post("/live/stop", status_code=202)
    def live_stop(request: Request):
        local_request(request)
        return recorder.stop()
