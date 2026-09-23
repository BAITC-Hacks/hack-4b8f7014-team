# Local model assets

Keep weights out of Git. Provision on a connected setup machine, verify licenses and checksums,
then transfer to the closed network. Runtime must never download missing weights.

- `whisper/`: complete CTranslate2 faster-whisper multilingual model snapshot (not `.en`).
- `diarization/`: complete pyannote Community-1 checkout including Git LFS weights.
- Ollama stores LLM weights in its own configured local model store.

Use explicit paths with `WhisperModel(path, local_files_only=True)` and
`Pipeline.from_pretrained(local_directory)` for pyannote. Community-1 requires accepting
the upstream model conditions during provisioning. Do not use a cloud diarization variant.
For Ollama provision a multilingual model locally and disable cloud features in the server
environment (`OLLAMA_NO_CLOUD=1`). Model selection and RU/KZ quality require evaluation.

References: [faster-whisper](https://github.com/SYSTRAN/faster-whisper),
[Community-1 offline instructions](https://huggingface.co/pyannote/speaker-diarization-community-1),
[Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs).
