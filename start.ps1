$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
if (!(Test-Path -LiteralPath ".venv/Scripts/python.exe")) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Python 3.11 or later is required." }
    & .venv/Scripts/python.exe -m pip install -r requirements-lock.txt
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
}
if (!(Test-Path -LiteralPath ".env")) { Copy-Item -LiteralPath .env.example -Destination .env }
Write-Host "Open http://localhost:4180 for AgentGate product research. You can use the local demo or create a private account."
& .venv/Scripts/python.exe -m uvicorn app:app --host 127.0.0.1 --port 4180
