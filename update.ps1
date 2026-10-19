<#
.SYNOPSIS
  Updates an existing PolarnikTTS installation (e.g. C:\PolarnikTTS) to the latest version
  from GitHub, keeping config.yaml, voice samples, downloaded models and the GPU engine
  environments. Windows PowerShell 5.1 compatible, no git needed.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File C:\PolarnikTTS\update.ps1
  .\update.ps1 -Branch main
  .\update.ps1 -Zip D:\Downloads\PolarnikTTS-main.zip     # offline: use an already downloaded zip

.NOTES
  In a git clone use "git pull" instead - this script refuses to run there.
  Kept (never overwritten): server\config.yaml, server\.venv, server\envs, server\models,
  server\voices, server\logs, server\cache, host\pl.polarnik.launcher.json, host\polarnik_host.bat.
#>
param(
  [string]$Branch = "main",
  [string]$Repo = "mrtipeq/PolarnikTTS",
  [string]$Zip = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$server = Join-Path $root "server"
$vpy = Join-Path $server ".venv\Scripts\python.exe"

if (Test-Path (Join-Path $root ".git")) {
  throw "$root is a git clone - update it with 'git pull' (then re-run install.ps1 if dependencies changed)."
}
if (-not (Test-Path $vpy)) {
  throw "No server\.venv in $root - this does not look like an installed PolarnikTTS. Run install.ps1 instead."
}

function Get-InstalledVersion {
  $init = Join-Path $server "polarnik_server\__init__.py"
  if (Test-Path $init) {
    $m = Select-String -Path $init -Pattern '__version__\s*=\s*"([^"]+)"'
    if ($m) { return $m.Matches[0].Groups[1].Value }
  }
  return "?"
}
$before = Get-InstalledVersion
Write-Host "Installed server version: $before"

# 1. Download and unpack the new version
$tmp = Join-Path $env:TEMP ("polarnik-update-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
  if (-not $Zip) {
    $Zip = Join-Path $tmp "src.zip"
    $url = "https://github.com/$Repo/archive/refs/heads/$Branch.zip"
    Write-Host "Downloading $url"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $url -OutFile $Zip -UseBasicParsing
  }
  Write-Host "Unpacking"
  Expand-Archive -Path $Zip -DestinationPath (Join-Path $tmp "src") -Force
  $src = Get-ChildItem (Join-Path $tmp "src") -Directory | Select-Object -First 1
  if (-not $src -or -not (Test-Path (Join-Path $src.FullName "server\polarnik_server"))) {
    throw "The archive does not contain a PolarnikTTS source tree."
  }

  # 2. Stop the running server and its engine workers (they lock files in server\)
  Write-Host "Stopping the PolarnikTTS server"
  Get-CimInstance Win32_Process |
    Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match '-m polarnik_server' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  Start-Sleep -Seconds 2

  # 3. Copy the new files over the installation (nothing is deleted, user data is excluded)
  Write-Host "Copying files into $root"
  $xd = @(".venv", "envs", "models", "voices", "logs", "cache", "__pycache__")
  $xf = @("config.yaml", "pl.polarnik.launcher.json", "polarnik_host.bat", "polarnik_host.sh")
  & robocopy $src.FullName $root /E /NFL /NDL /NJH /NJS /NP /XD $xd /XF $xf | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy failed (exit code $LASTEXITCODE)" }

  # 4. Refresh the server package and its light extras in server\.venv
  $extras = @("edge")
  & $vpy -c "import piper" 2>$null
  if ($LASTEXITCODE -eq 0) { $extras += "piper" }
  $spec = "$server[$($extras -join ',')]"
  Write-Host "Updating Python packages: -e $spec"
  & $vpy -m pip install --upgrade --upgrade-strategy only-if-needed -e $spec
  if ($LASTEXITCODE -ne 0) { throw "pip install failed (exit code $LASTEXITCODE)" }

  # 5. Re-register the Chrome launcher (native messaging host) for this folder
  & (Join-Path $root "install_host.ps1")
}
finally {
  Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}

$after = Get-InstalledVersion
Write-Host ""
Write-Host "Updated: server $before -> $after."
Write-Host "Start the server from the extension (popup -> Start) or with .\run_server.ps1."
