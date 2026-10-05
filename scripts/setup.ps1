# ==============================================================================
# MIA setup for an existing checkout (e.g. after `git clone`).
# Uses the same installer as the one-line install, but for this folder:
# private Python environment, dependencies, the `mia` command, then `mia onboard`.
# Keep this file ASCII-only (Windows PowerShell 5.1 misreads other characters).
# ==============================================================================

$repoRoot = Split-Path -Parent $PSScriptRoot
$env:MIA_PROJECT_DIR = $repoRoot
try {
    & (Join-Path $repoRoot 'install.ps1')
} finally {
    Remove-Item Env:\MIA_PROJECT_DIR -ErrorAction SilentlyContinue
}
