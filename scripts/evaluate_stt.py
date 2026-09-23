"""Small reproducible local STT comparison, not a meeting-quality benchmark."""
import argparse
import gc
import json
import re
import time
from pathlib import Path

from app.adapters import offline_environment
from app.gpu import cuda_libraries


def words(text):
    return re.findall(r"\w+", text.lower().replace("ё", "е"))


def word_errors(reference, hypothesis):
    left, right = words(reference), words(hypothesis)
    previous = list(range(len(right) + 1))
    for i, token in enumerate(left, 1):
        current = [i]
        for j, other in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j - 1] + (token != other)))
        previous = current
    return previous[-1], len(left)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute", default="int8")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    offline_environment()
    from faster_whisper import WhisperModel

    manifest = json.loads(Path("data/eval/manifest.json").read_text(encoding="utf-8"))
    result = []
    with cuda_libraries(args.device):
        model = WhisperModel(args.model, device=args.device, compute_type=args.compute,
                             local_files_only=True)
        for sample in manifest:
            started = time.monotonic()
            segments, _ = model.transcribe(sample["path"], language=sample["language"],
                                           vad_filter=True, word_timestamps=True)
            hypothesis = " ".join(s.text for s in segments)
            errors, count = word_errors(sample["reference"], hypothesis)
            result.append({**sample, "hypothesis": hypothesis, "errors": errors,
                           "reference_words": count, "seconds": round(time.monotonic() - started, 2)})
            print(sample["language"], sample["filename"], errors, count, flush=True)
        del model
        gc.collect()
    Path(args.output).write_text(json.dumps({"model": args.model, "device": args.device,
        "compute": args.compute, "samples": result}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
