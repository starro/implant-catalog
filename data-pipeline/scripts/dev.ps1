# Dagster UI (포트 3333) — DATA_ROOT/DAGSTER_HOME 자동 설정
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not $env:DATA_ROOT)    { $env:DATA_ROOT    = (Join-Path (Get-Location) "data") }
if (-not $env:DAGSTER_HOME) { $env:DAGSTER_HOME = (Join-Path (Get-Location) ".dagster_home") }
if (-not $env:HF_HOME)      { $env:HF_HOME      = "c:\dev\image-origin-poc\hf_cache" }
New-Item -ItemType Directory -Force $env:DATA_ROOT, $env:DAGSTER_HOME | Out-Null

$py = ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "c:\dev\image-origin-poc\.venv\Scripts\python.exe" }

Write-Host "DATA_ROOT=$env:DATA_ROOT"
Write-Host "DAGSTER_HOME=$env:DAGSTER_HOME"
& $py -m dagster dev -m drheri_pipeline.definitions --port 3333
