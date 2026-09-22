<#
.SYNOPSIS
  Installs the PolarnikTTS engine server on Windows (creates server\.venv, installs extras, downloads Piper voices).

.EXAMPLE
  .\install.ps1                              # base + edge-tts + piper (no GPU needed)
  .\install.ps1 -Extras edge,piper,chatterbox   # also installs Chatterbox into server\envs\chatterbox
  (GPU engines can also be installed later from the extension's options page)

.PARAMETER Extras
  Comma-separated list of extras from server\pyproject.toml: edge, piper, chatterbox, xtts, elevenlabs, all.
.PARAMETER Cuda
  Kept for compatibility; GPU engines now pick their own CUDA build automatically (isolated envs).
#>
param(
  [string]$Extras = "edge,piper",
  [string]$Cuda = "",
  [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$server = Join-Path $root "server"

function Find-Python {
  if ($Python) { return $Python }
  foreach ($cand in @("py -3.12", "py -3.11", "py -3.10", "python3", "python")) {
    try {
      $v = & cmd /c "$cand -c `"import sys;print(sys.version_info[0]*100+sys.version_info[1])`"" 2>$null
      if ($LASTEXITCODE -eq 0 -and [int]$v -ge 310) { return $cand }
    } catch {}
  }
  throw "Python 3.10+ not found. Install it from https://www.python.org/downloads/ (tick 'Add to PATH')."
}

$py = Find-Python
Write-Host "Using Python: $py"

$venv = Join-Path $server ".venv"
if (-not (Test-Path $venv)) {
  Write-Host "Creating virtualenv $venv"
  & cmd /c "$py -m venv `"$venv`""
}
$pip = Join-Path $venv "Scripts\pip.exe"
$vpy = Join-Path $venv "Scripts\python.exe"

function Invoke-Checked {
  param([string]$Description, [scriptblock]$Command)
  & $Command
  if ($LASTEXITCODE -ne 0) { throw "$Description failed (exit code $LASTEXITCODE)" }
}

Invoke-Checked "pip upgrade" { & $vpy -m pip install --upgrade pip wheel }

$extrasList = $Extras.Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ }
# Heavy GPU engines live in isolated virtualenvs (server\envs\<engine>) - handled after the base install
$heavy = @($extrasList | Where-Object { $_ -in @("chatterbox", "xtts") })
$extrasList = @($extrasList | Where-Object { $_ -notin @("chatterbox", "xtts") })
if (-not $extrasList) { $extrasList = @("edge") }

$spec = "$server[$($extrasList -join ',')]"
Write-Host "Installing server package: -e $spec"
Invoke-Checked "server package install" { & $pip install -e $spec }

$cfg = Join-Path $server "config.yaml"
if (-not (Test-Path $cfg)) {
  Copy-Item (Join-Path $server "config.example.yaml") $cfg
  Write-Host "Created $cfg - edit it to enable engines / API keys."
}

if ($extrasList -contains "piper" -or $extrasList -contains "all") {
  Write-Host "Downloading Piper Polish voices"
  Push-Location $server
  try { Invoke-Checked "Piper voice download" { & $vpy (Join-Path $server "scripts\download_models.py") piper } }
  finally { Pop-Location }
}

foreach ($h in $heavy) {
  Write-Host "Installing $h into its isolated environment (this downloads several GB)"
  Push-Location $server
  try { Invoke-Checked "$h install" { & $vpy (Join-Path $server "scripts\install_engine.py") $h } }
  finally { Pop-Location }
}

# Native messaging host - lets the extension start the server on demand (per-user registry keys)
& (Join-Path $root "install_host.ps1")

Write-Host ""
Write-Host "Done. Start the server with:  .\run_server.ps1"
Write-Host "Then load extension\ in Chrome: chrome://extensions -> Developer mode -> Load unpacked."
