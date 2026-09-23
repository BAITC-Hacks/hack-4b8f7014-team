# Closed-network deployment plan

The current base binds both web services to loopback and uses local SQLite/files. It has no
authentication and is intended for one trusted operator. Before exposing it on a network,
add an authenticated TLS reverse proxy, authorization for meeting access and an audit trail.
Do not expose the Ollama port to users or the internet.

1. On a connected staging machine matching the target OS, Python and accelerator, resolve
   dependencies, review licenses, create a locked dependency set and wheelhouse. Include
   FFmpeg, Ollama, required torch/torchcodec libraries and licensed Unicode export fonts.
2. Provision complete STT/diarization snapshots and Ollama weights. Verify checksums and
   transfer artifacts to the closed network. Keep credentials used for provisioning out of Git.
3. Install from the local wheelhouse with `pip install --no-index --find-links wheelhouse
   -r requirements.txt` after verifying all dependencies are present. Use the staging lock
   for reproducible production installs. GPU builds require matching drivers and libraries.
4. Set offline variables in the service manager's environment before model imports:
   `HF_HUB_OFFLINE=1`, `HF_HUB_DISABLE_TELEMETRY=1`, `PYANNOTE_METRICS_ENABLED=0`.
   Set `OLLAMA_NO_CLOUD=1` in the **Ollama server** environment. `.env` settings alone do
   not configure a separately running model server. No runtime auto-download or cloud fallback.
5. Run under a dedicated non-admin account, restrict filesystem access to `data/`, encrypt
   storage/backups as required, set upload limits at the reverse proxy, and deny outbound
   network access at the host firewall. Streamlit analytics are disabled in committed config.
6. Test upload/task operations with internet disconnected. Once implemented, test the whole
   pipeline offline with missing-weight failures and network capture. Document hardware and
   benchmark results before claiming on-prem readiness.

Use service supervision for FastAPI, Streamlit, future worker and Ollama. Persist `data/` and
model directories across restarts. Establish retention/deletion, backups and restore testing;
avoid transcript content in application logs. The scaffold does not implement encryption,
user management, malware scanning, scheduling or production deployment automation.
