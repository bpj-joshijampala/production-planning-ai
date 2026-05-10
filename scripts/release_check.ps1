$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"

function Invoke-ReleaseStep {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Name,

    [Parameter(Mandatory = $true)]
    [scriptblock]$Command
  )

  Write-Host ""
  Write-Host "==> $Name"
  & $Command
  $succeeded = $?
  $exitCode = $LASTEXITCODE

  if (-not $succeeded -or ($null -ne $exitCode -and $exitCode -ne 0)) {
    if ($null -eq $exitCode) {
      throw "$Name failed."
    }

    throw "$Name failed with exit code $exitCode."
  }
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
  throw "Python virtual environment was not found at $pythonPath. Run backend setup first."
}

Push-Location -LiteralPath $repoRoot
try {
  Invoke-ReleaseStep -Name "Backend tests" -Command { & $pythonPath -m pytest backend\tests }
  Invoke-ReleaseStep -Name "Backend lint" -Command { & $pythonPath -m ruff check backend\app backend\tests }

  Push-Location -LiteralPath frontend
  try {
    Invoke-ReleaseStep -Name "Frontend tests" -Command { npm test }
    Invoke-ReleaseStep -Name "Frontend build" -Command { npm run build }
  }
  finally {
    Pop-Location
  }
}
finally {
  Pop-Location
}
