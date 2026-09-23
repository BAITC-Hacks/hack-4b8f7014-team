import argparse
import json
import time
from pathlib import Path

from app.config import Settings
from app.extraction import GroundedExtractor
from app.schemas import ProcessOptions, Segment


def main():
    p = argparse.ArgumentParser(
        description="Compare grounded extraction on a saved local transcript; no reference protocol is supplied."
    )
    p.add_argument("--model", required=True)
    p.add_argument("--transcript", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    segments = [
        Segment.model_validate(x) for x in json.loads(args.transcript.read_text(encoding="utf-8"))
    ]
    extractor = GroundedExtractor(Settings(ollama_model=args.model))
    started = time.monotonic()
    summary, tasks = extractor.extract(segments, ProcessOptions())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "model": args.model,
                "seconds": round(time.monotonic() - started, 2),
                "summary": summary,
                "tasks": [t.model_dump(mode="json") for t in tasks],
                "report_points": [p.model_dump() for p in extractor.report_points],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("Completed:", len(tasks), "draft tasks")


if __name__ == "__main__":
    main()
