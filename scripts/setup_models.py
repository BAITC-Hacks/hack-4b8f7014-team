"""Explicit online provisioning. Never called by runtime processing."""
import argparse
import json
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("component", choices=["whisper", "whisper-large-v3", "diarization"])
    parser.add_argument("--revision", help="Pin a model revision for repeatable provisioning")
    args = parser.parse_args()
    repo = {"whisper": "Systran/faster-whisper-small",
            "whisper-large-v3": "Systran/faster-whisper-large-v3",
            "diarization": "pyannote/speaker-diarization-community-1"}[args.component]
    target = Path("models") / args.component
    revision = HfApi().model_info(repo, revision=args.revision).sha
    snapshot_download(repo, revision=revision, local_dir=target,
                      ignore_patterns=["*.md", ".gitattributes"])
    (target / "provisioning.json").write_text(
        json.dumps({"repository": repo, "revision": revision}, indent=2), encoding="utf-8")
    print(f"Installed {repo} at revision {revision} into {target}")


if __name__ == "__main__":
    main()
