# 파이프라인 서버 종료 — FiftyOne(:5151)+mongod, Dagster(:3333).
# 포트 지정: .\scripts\stop.ps1 5151
param([int[]]$Ports = @(5151, 3333))

foreach ($port in $Ports) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($conns) {
        foreach ($c in $conns) {
            Write-Host "port $port -> PID $($c.OwningProcess) 종료"
            Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    } else {
        Write-Host "port $port -> 리스너 없음"
    }
}

if ($Ports -contains 5151) {
    Get-Process mongod -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Host "mongod PID $($_.Id) 종료"
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
}
Write-Host "완료."
