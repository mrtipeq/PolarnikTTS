<#
.SYNOPSIS
  Starts the PolarnikTTS engine server automatically with Windows (no console window).

.DESCRIPTION
  Creates a shortcut in the current user's Startup folder that runs
  server\.venv\Scripts\pythonw.exe -m polarnik_server, and starts the server right away.
  No administrator rights needed. Logs go to server\logs\server.log.

.EXAMPLE
  .\autostart.ps1              # install autostart + start now
  .\autostart.ps1 -Uninstall   # remove autostart (a running server keeps running)
  .\autostart.ps1 -Status
#>
param([switch]$Uninstall, [switch]$Status)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$server = Join-Path $root "server"
$pyw = Join-Path $server ".venv\Scripts\pythonw.exe"
$startup = [Environment]::GetFolderPath("Startup")
$lnk = Join-Path $startup "PolarnikTTS server.lnk"

function Test-ServerUp {
  try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "http://127.0.0.1:8765/health"; return $r.StatusCode -eq 200 } catch { return $false }
}

if ($Status) {
  Write-Host ("Autostart shortcut: " + $(if (Test-Path $lnk) { "installed ($lnk)" } else { "not installed" }))
  Write-Host ("Server on 127.0.0.1:8765: " + $(if (Test-ServerUp) { "running" } else { "not running" }))
  exit 0
}

if ($Uninstall) {
  if (Test-Path $lnk) { Remove-Item $lnk; Write-Host "Removed $lnk" } else { Write-Host "Autostart was not installed." }
  exit 0
}

if (-not (Test-Path $pyw)) { throw "Virtualenv not found ($pyw) - run .\install.cmd first." }

$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($lnk)
$sc.TargetPath = $pyw
$sc.Arguments = "-m polarnik_server --config `"$(Join-Path $server 'config.yaml')`""
$sc.WorkingDirectory = $server
$sc.WindowStyle = 7   # minimized (pythonw has no window anyway)
$sc.IconLocation = "$pyw,0"
$sc.Description = "PolarnikTTS engine server (background)"
$sc.Save()
Write-Host "Installed autostart shortcut: $lnk"

if (Test-ServerUp) {
  Write-Host "Server is already running."
} else {
  Start-Process -FilePath $pyw -ArgumentList $sc.Arguments -WorkingDirectory $server -WindowStyle Hidden
  Start-Sleep -Seconds 3
  Write-Host ("Server started in the background: " + $(if (Test-ServerUp) { "OK (http://127.0.0.1:8765)" } else { "not responding yet - check server\logs\server.log" }))
}
