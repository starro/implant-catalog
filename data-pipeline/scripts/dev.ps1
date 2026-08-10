# 관리 UI(uvicorn, 포트 3000) — DATA_ROOT 자동 설정
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not $env:DATA_ROOT)    { $env:DATA_ROOT    = (Join-Path (Get-Location) "data") }
if (-not $env:HF_HOME)      { $env:HF_HOME      = "c:\dev\image-origin-poc\hf_cache" }
New-Item -ItemType Directory -Force $env:DATA_ROOT | Out-Null

$py = ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "c:\dev\image-origin-poc\.venv\Scripts\python.exe" }

Write-Host "DATA_ROOT=$env:DATA_ROOT"
& $py -m uvicorn drheri_pipeline.ui.app:app --port 3000
