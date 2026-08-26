# ==============================================================================
# MIA Startup Script
# Runs the FastAPI server and optionally starts a Cloudflare quick tunnel.
# ==============================================================================

$repoRoot = (Get-Item -Path ".\").FullName
$envPath = Join-Path $repoRoot ".env"

if (-not (Test-Path $envPath)) {
    Write-Host "❌ .env file not found! Please run '.\scripts\setup.ps1' first." -ForegroundColor Red
    exit 1
}

Write-Host "╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║        🚀 STARTING MIA                 ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════╝" -ForegroundColor Cyan

# Check if user wants a Cloudflare Tunnel
Write-Host "`nDo you want to expose MIA to the internet via Cloudflare Quick Tunnel?"
Write-Host "This will generate a temporary public URL without needing a domain name."
$useTunnel = Read-Host "Use Tunnel? (y/n) [Default: n]"

if ($useTunnel.ToLower() -eq 'y') {
    # Check if cloudflared is installed
    $cfCheck = Get-Command "cloudflared" -ErrorAction SilentlyContinue
    if ($null -eq $cfCheck) {
        Write-Host "`nCloudflared is not installed. Installing via winget..." -ForegroundColor Yellow
        winget install --id Cloudflare.cloudflared
        if ($LASTEXITCODE -ne 0) {
            Write-Host "❌ Failed to install cloudflared. Please install it manually or run without tunnel." -ForegroundColor Red
            exit 1
        }
        # Refresh env path for cloudflared
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    }

    Write-Host "`nStarting FastAPI Server in the background..." -ForegroundColor Yellow
    # Start uvicorn in a separate process
    $serverProcess = Start-Process -FilePath "python" -ArgumentList "-m uvicorn server.main:app --host 0.0.0.0 --port 8765" -PassThru -NoNewWindow
    
    Start-Sleep -Seconds 3 # Wait for server to bind

    Write-Host "`nStarting Cloudflare Quick Tunnel..." -ForegroundColor Yellow
    Write-Host "Look for the URL ending in '.trycloudflare.com' below." -ForegroundColor Cyan
    Write-Host "Press Ctrl+C to stop both the tunnel and the server." -ForegroundColor Yellow
    Write-Host "--------------------------------------------------------"
    
    try {
        # Run tunnel in foreground so user sees URL and can Ctrl+C
        cloudflared tunnel --url http://localhost:8765
    } finally {
        # Ensure server is stopped when script exits
        Write-Host "`nStopping server..."
        Stop-Process -Id $serverProcess.Id -Force
    }

} else {
    # Run server locally only
    Write-Host "`nStarting FastAPI Server..." -ForegroundColor Yellow
    Write-Host "Available at: http://localhost:8765" -ForegroundColor Cyan
    Write-Host "Press Ctrl+C to stop." -ForegroundColor Yellow
    Write-Host "--------------------------------------------------------"
    python -m uvicorn server.main:app --host 0.0.0.0 --port 8765
}
