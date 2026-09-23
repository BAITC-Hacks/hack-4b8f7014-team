$ErrorActionPreference = 'Stop'
$projectDir = Split-Path $PSScriptRoot -Parent
Set-Location $projectDir
$pythonExe = Join-Path $projectDir '.venv/Scripts/python.exe'
if (-not (Test-Path $pythonExe)) { throw 'Create .venv and install requirements-local.txt first.' }
New-Item -ItemType Directory -Force data | Out-Null
$ollamaExe = Join-Path $projectDir 'data/runtime/ollama/ollama.exe'
$env:OLLAMA_MODELS = Join-Path $projectDir 'models/ollama'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_HOST = '127.0.0.1:11434'
if (-not (Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue)) {
    if (-not (Test-Path $ollamaExe)) { throw 'Install the portable Ollama runtime in data/runtime/ollama first.' }
    Start-Process -FilePath $ollamaExe -ArgumentList serve -WorkingDirectory $projectDir -WindowStyle Hidden -RedirectStandardOutput data/ollama.log -RedirectStandardError data/ollama-error.log
}
if (-not (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath $pythonExe -ArgumentList '-m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000' -WorkingDirectory $projectDir -WindowStyle Hidden -RedirectStandardOutput data/api.log -RedirectStandardError data/api-error.log
}
if (-not (Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath $pythonExe -ArgumentList '-m streamlit run app/ui.py --server.headless true' -WorkingDirectory $projectDir -WindowStyle Hidden -RedirectStandardOutput data/ui.log -RedirectStandardError data/ui-error.log
}
# A second worker exits safely if the existing worker owns its OS lock.
Start-Process -FilePath $pythonExe -ArgumentList '-m app.worker' -WorkingDirectory $projectDir -WindowStyle Hidden
Write-Output 'Open http://127.0.0.1:8501. Diagnostics: data/*-error.log'
