"""One durable local worker: python -m app.worker [--once]."""
import argparse
import time

from filelock import FileLock, Timeout

from app.adapters import PipelineError
from app.config import Settings
from app.pipeline import Pipeline
from app.storage import Store


def run_once(store, pipeline):
    meeting = store.claim()
    if meeting is None:
        return False
    try:
        minutes = pipeline.run(meeting, lambda stage: store.progress(meeting.id, stage))
        store.complete(minutes)
    except Exception as exc:
        error = str(exc) if isinstance(exc, PipelineError) else (
            f"Ошибка {type(exc).__name__}. Проверьте зависимости, веса и локальный Ollama.")
        store.progress(meeting.id, "failed", error=error)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Process at most one queued meeting")
    args = parser.parse_args()
    settings = Settings()
    store = Store(settings.data_dir)
    try:
        with FileLock(str(settings.data_dir / "worker.lock"), timeout=0):
            store.recover()
            pipeline = Pipeline(settings)
            while True:
                processed = run_once(store, pipeline)
                if args.once:
                    break
                if not processed:
                    time.sleep(1)
    except Timeout:
        parser.exit(1, "Another worker already owns this data directory.\n")


if __name__ == "__main__":
    main()
