# ==============================================================================
# MIA installer for Windows
#
#   irm https://raw.githubusercontent.com/darshanpatel4/MIA/main/install.ps1 | iex
#
# Installs (or updates) MIA, gives you a `mia` command, then runs `mia onboard`.
# Nothing needs admin rights. Optional overrides (set before running):
#   $env:MIA_HOME         install folder              (default: $HOME\MIA)
#   $env:MIA_REPO         GitHub repository URL       (default: https://github.com/darshanpatel4/MIA)
#   $env:MIA_BRANCH       branch to install           (default: main)
#   $env:MIA_PROJECT_DIR  use an existing checkout instead of downloading (used by scripts\setup.ps1)
#   $env:MIA_NO_ONBOARD   set to 1 to skip the setup wizard at the end
# Keep this file ASCII-only: Windows PowerShell 5.1 misreads other characters in script files.
# ==============================================================================

function Install-MIA {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'   # Invoke-WebRequest is very slow with the progress bar on PS 5.1
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    $repo   = if ($env:MIA_REPO)   { $env:MIA_REPO.TrimEnd('/') } else { 'https://github.com/darshanpatel4/MIA' }
    $branch = if ($env:MIA_BRANCH) { $env:MIA_BRANCH } else { 'main' }
    $binDir = Join-Path $env:LOCALAPPDATA 'MIA\bin'

    function Step($n, $total, $text) { Write-Host ""; Write-Host "[$n/$total] $text" -ForegroundColor Cyan }
    function Ok($text)   { Write-Host "  OK  $text" -ForegroundColor Green }
    function Warn($text) { Write-Host "  !!  $text" -ForegroundColor Yellow }
    function Fail($text) { Write-Host "  XX  $text" -ForegroundColor Red; throw "MIA install stopped: $text" }

    function Refresh-Path {
        $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
    }

    # Returns the path of a Python >= 3.10 interpreter, or $null.
    function Find-Python {
        $candidates = @()
        if (Get-Command py -ErrorAction SilentlyContinue) { $candidates += ,@('py', '-3') }
        foreach ($name in 'python', 'python3') {
            $cmd = Get-Command $name -ErrorAction SilentlyContinue
            # Skip the Microsoft Store placeholder, which opens the Store instead of running Python
            if ($cmd -and $cmd.Source -notlike '*\WindowsApps\*') { $candidates += ,@($cmd.Source) }
        }
        foreach ($c in $candidates) {
            try {
                $exe = $c[0]; $pre = @($c | Select-Object -Skip 1)
                $out = & $exe @pre -c "import sys; print(sys.executable if sys.version_info >= (3, 10) else '')" 2>$null
                if ($LASTEXITCODE -eq 0 -and $out -and (Test-Path $out.Trim())) { return $out.Trim() }
            } catch { }
        }
        return $null
    }

    Write-Host ""
    Write-Host "  __  __ ___    _    " -ForegroundColor Cyan
    Write-Host " |  \/  |_ _|  /_\   " -ForegroundColor Cyan
    Write-Host " | |\/| || |  / _ \  " -ForegroundColor Cyan
    Write-Host " |_|  |_|___|/_/ \_\ " -ForegroundColor Cyan
    Write-Host " Your personal AI agent for Windows" -ForegroundColor DarkGray

    # --- 1. Python ------------------------------------------------------------
    Step 1 5 'Checking Python (3.10 or newer)'
    $python = Find-Python
    if (-not $python) {
        Warn 'Python 3.10+ was not found.'
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            Fail 'Install Python 3.12 from https://www.python.org/downloads/ (tick "Add to PATH"), then run this installer again.'
        }
        Write-Host '  Installing Python 3.12 with winget (for your user only)...'
        winget install -e --id Python.Python.3.12 --scope user --accept-source-agreements --accept-package-agreements | Out-Host
        Refresh-Path
        $python = Find-Python
        if (-not $python) {
            $guess = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
            if (Test-Path $guess) { $python = $guess }
        }
        if (-not $python) { Fail 'Python was installed but could not be found. Open a new PowerShell window and run the installer again.' }
    }
    Ok "Python: $python"

    # --- 2. Get MIA -------------------------------------------------------------
    if ($env:MIA_PROJECT_DIR) {
        Step 2 5 'Using existing MIA folder'
        $miaDir = (Resolve-Path $env:MIA_PROJECT_DIR).Path
        if (-not (Test-Path (Join-Path $miaDir 'mia.py'))) { Fail "$miaDir does not contain mia.py" }
        Ok $miaDir
    } else {
        $miaDir = if ($env:MIA_HOME) { $env:MIA_HOME } else { Join-Path $HOME 'MIA' }
        $isUpdate = Test-Path (Join-Path $miaDir 'mia.py')
        Step 2 5 $(if ($isUpdate) { "Updating MIA in $miaDir" } else { "Downloading MIA to $miaDir" })

        if (Get-Command git -ErrorAction SilentlyContinue) {
            if (Test-Path (Join-Path $miaDir '.git')) {
                git -C $miaDir pull --ff-only | Out-Host
                if ($LASTEXITCODE -ne 0) { Warn 'git pull failed (local changes?). Keeping the current version.' }
            } elseif (-not $isUpdate) {
                git clone --depth 1 --branch $branch "$repo.git" $miaDir | Out-Host
                if ($LASTEXITCODE -ne 0) { Fail "Could not clone $repo" }
            } else {
                Warn 'This folder was not installed with git; downloading the latest files over it.'
                $isUpdate = $true; $useZip = $true
            }
        } else {
            $useZip = $true
        }

        if ($useZip) {
            # Download the branch as a zip and copy it over. .env and data/ are not in the zip, so settings are kept.
            $tmp = Join-Path ([IO.Path]::GetTempPath()) ("mia-" + [Guid]::NewGuid().ToString('N'))
            New-Item -ItemType Directory -Path $tmp | Out-Null
            try {
                $zip = Join-Path $tmp 'mia.zip'
                Invoke-WebRequest -UseBasicParsing -Uri "$repo/archive/refs/heads/$branch.zip" -OutFile $zip
                Expand-Archive -Path $zip -DestinationPath $tmp -Force
                $src = Get-ChildItem -Path $tmp -Directory | Select-Object -First 1
                New-Item -ItemType Directory -Path $miaDir -Force | Out-Null
                Copy-Item -Path (Join-Path $src.FullName '*') -Destination $miaDir -Recurse -Force
            } finally {
                Remove-Item -Path $tmp -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
        Ok $miaDir
    }

    # --- 3. Private Python environment + dependencies ---------------------------
    Step 3 5 'Installing MIA''s dependencies (first time takes a few minutes)'
    $venv = Join-Path $miaDir '.venv'
    $venvPython = Join-Path $venv 'Scripts\python.exe'
    if (-not (Test-Path $venvPython)) {
        & $python -m venv $venv
        if ($LASTEXITCODE -ne 0) { Fail 'Could not create the Python environment.' }
    }
    & $venvPython -m pip install --upgrade pip --quiet --disable-pip-version-check | Out-Null
    & $venvPython -m pip install -r (Join-Path $miaDir 'server\requirements.txt') --quiet --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { Fail 'Installing dependencies failed (see the messages above).' }
    Ok 'Dependencies installed'

    # --- 4. The `mia` command ---------------------------------------------------
    Step 4 5 'Adding the "mia" command'
    New-Item -ItemType Directory -Path $binDir -Force | Out-Null
    $shim = "@echo off`r`nset PYTHONUTF8=1`r`n`"$venvPython`" `"$(Join-Path $miaDir 'mia.py')`" %*`r`n"
    [IO.File]::WriteAllText((Join-Path $binDir 'mia.cmd'), $shim, [Text.Encoding]::ASCII)
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    if (-not $userPath) { $userPath = '' }
    if (($userPath -split ';') -notcontains $binDir) {
        [Environment]::SetEnvironmentVariable('Path', ($userPath.TrimEnd(';') + ";$binDir").TrimStart(';'), 'User')
    }
    if (($env:Path -split ';') -notcontains $binDir) { $env:Path = "$env:Path;$binDir" }
    Ok "mia -> $miaDir"

    # --- 5. Setup wizard --------------------------------------------------------
    Step 5 5 'Setup'
    if ($env:MIA_NO_ONBOARD -eq '1') {
        Ok 'Skipped. Run "mia onboard" when you are ready.'
    } else {
        & (Join-Path $binDir 'mia.cmd') onboard
    }

    Write-Host ""
    Write-Host "MIA is installed. Useful commands:" -ForegroundColor Green
    Write-Host "  mia start      start MIA"
    Write-Host "  mia status     check that everything is set up"
    Write-Host "  mia model      change the AI model"
    Write-Host "  mia onboard    run the setup wizard again"
    Write-Host "  mia update     update to the latest version"
    Write-Host "(Open a new terminal window if the mia command is not found.)" -ForegroundColor DarkGray
}

try {
    Install-MIA
} catch {
    Write-Host ""
    Write-Host $_.Exception.Message -ForegroundColor Red
}
