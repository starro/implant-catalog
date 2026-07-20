# FiftyOne 검수 앱 실행 (포트 5151) — brand×stage saved view 생성 후 App
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not $env:DATA_ROOT) { $env:DATA_ROOT = (Join-Path (Get-Location) "data") }
$env:PYTHONPATH = (Get-Location).Path
$env:PYTHONIOENCODING = "utf-8"

$py = ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "c:\dev\image-origin-poc\.venv\Scripts\python.exe" }

Write-Host "DATA_ROOT=$env:DATA_ROOT"
Write-Host "App -> http://localhost:5151  (view 드롭다운: <brand>-review / <brand>-training)"
& $py scripts/fiftyone_review.py
