# ==============================================================================
# Start MIA (same as `mia start`). Pass -Tunnel to force a Cloudflare Quick Tunnel;
# otherwise the "remote access" choice from `mia onboard` is used.
# Keep this file ASCII-only (Windows PowerShell 5.1 misreads other characters).
# ==============================================================================

param([switch]$Tunnel)

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
$python = if (Test-Path $venvPython) { $venvPython } else { 'python' }

if (-not (Test-Path (Join-Path $repoRoot '.env'))) {
    Write-Host 'MIA is not set up yet. Running the setup wizard first...' -ForegroundColor Yellow
    & $python (Join-Path $repoRoot 'mia.py') onboard
    exit
}

$env:PYTHONUTF8 = '1'
$arguments = @((Join-Path $repoRoot 'mia.py'), 'start')
if ($Tunnel) { $arguments += '--tunnel' }
& $python @arguments
