# DeepShield helper (pure ASCII on purpose).
#   -Mode kill : synchronously kill any stale listener on port 8000.
#   -Mode wait : poll health for up to 3 min, open docs page when ready.
param([string]$Mode = "wait")
$ErrorActionPreference = "SilentlyContinue"

if ($Mode -eq "kill") {
  $conns = netstat -ano | Select-String ":8000.*LISTENING"
  foreach ($line in $conns) {
    $tok = ($line -split '\s+') | Where-Object { $_ -ne "" }
    $id = $tok[-1]
    if ($id -match '^\d+$' -and [int]$id -ne $PID) {
      Stop-Process -Id ([int]$id) -Force
    }
  }
  exit 0
}

$u = "http://localhost:8000/api/v1/health"
for ($i = 0; $i -lt 90; $i++) {
  try {
    $r = Invoke-WebRequest -Uri $u -TimeoutSec 2 -UseBasicParsing
    if ($r.StatusCode -eq 200) {
      Start-Process "http://localhost:8000/docs"
      break
    }
  } catch { }
  Start-Sleep -Seconds 2
}
