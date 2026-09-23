"""Explicit online provisioning. Never called by runtime processing."""
import argparse
import json
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("component", choices=["whisper", "diarization"])
    args = parser.parse_args()
    repo = ("Systran/faster-whisper-small" if args.component == "whisper"
            else "pyannote/speaker-diarization-community-1")
    target = Path("models") / args.component
    revision = HfApi().model_info(repo).sha
    snapshot_download(repo, revision=revision, local_dir=target,
                      ignore_patterns=["*.md", ".gitattributes"])
    (target / "provisioning.json").write_text(
        json.dumps({"repository": repo, "revision": revision}, indent=2), encoding="utf-8")
    print(f"Installed {repo} at revision {revision} into {target}")


if __name__ == "__main__":
    main()
