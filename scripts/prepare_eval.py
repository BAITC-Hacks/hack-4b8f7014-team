"""Download the first three archive samples per language; no private audio leaves this PC."""
import argparse
import csv
import io
import json
import tarfile
from pathlib import Path

import httpx
from huggingface_hub import HfApi


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", default="70bb2e84b976b7e960aa89f1c648e09c59f894dd")
    args = parser.parse_args()
    root = Path("data/eval")
    root.mkdir(parents=True, exist_ok=True)
    revision = args.revision or HfApi().dataset_info("google/fleurs").sha
    manifest = []
    for language in ("kk_kz", "ru_ru"):
        base = f"https://huggingface.co/datasets/google/fleurs/resolve/{revision}/data/{language}"
        with httpx.Client(follow_redirects=True, timeout=120) as client:
            response = client.get(base + "/test.tsv")
            response.raise_for_status()
            rows = list(csv.reader(io.StringIO(response.text), delimiter="\t"))
            by_name = {row[1]: row for row in rows}
            # Streaming stops after the first 3 audio members, without retaining the large archive.
            import urllib.request

            with urllib.request.urlopen(base + "/audio/test.tar.gz", timeout=120) as stream:
                with tarfile.open(fileobj=stream, mode="r|gz") as archive:
                    count = 0
                    for member in archive:
                        name = Path(member.name).name
                        if member.isfile() and name in by_name:
                            row = by_name[name]
                            audio = archive.extractfile(member).read()
                            destination = root / f"{language}-{name}"
                            destination.write_bytes(audio)
                            manifest.append({"path": str(destination), "language": language[:2],
                                             "reference": row[2], "dataset": "google/fleurs",
                                             "revision": revision, "split": "test", "filename": name})
                            count += 1
                            if count == 3:
                                break
        print(language, count, flush=True)
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
