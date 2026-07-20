# 대화형 라벨링 세션 (FiftyOne App + Python 프롬프트). 본인 터미널에서 실행.
# App 에서 샘플 선택 후 프롬프트:  label(series='SS2')  →  keep()  →  promote_keeps()
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not $env:DATA_ROOT) { $env:DATA_ROOT = (Join-Path (Get-Location) "data") }
$env:PYTHONPATH = (Get-Location).Path
$env:PYTHONIOENCODING = "utf-8"
$env:HF_HOME = "c:\dev\image-origin-poc\hf_cache"

$py = ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "c:\dev\image-origin-poc\.venv\Scripts\python.exe" }

Write-Host "라벨링 세션 시작 — App http://localhost:5151 / 프롬프트에서 label()·keep()·promote_keeps()"
& $py -i scripts/label_session.py
