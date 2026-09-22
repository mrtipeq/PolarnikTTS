<#
.SYNOPSIS
  Registers the PolarnikTTS native messaging host so the Chrome extension can start the
  engine server on demand ("Uruchom serwer" button). Current user only, no admin rights.

.EXAMPLE
  .\install_host.ps1                # register for Chrome (and Edge/Chromium/Brave if present)
  .\install_host.ps1 -Uninstall
#>
param([switch]$Uninstall)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$server = Join-Path $root "server"
$hostDir = Join-Path $root "host"
$name = "pl.polarnik.launcher"
$extId = (Get-Content (Join-Path $hostDir "EXTENSION_ID") -Raw).Trim()
$py = Join-Path $server ".venv\Scripts\python.exe"
$bat = Join-Path $hostDir "polarnik_host.bat"
$manifest = Join-Path $hostDir "$name.json"

# Registry roots of Chromium-based browsers (HKCU = per user, no admin needed)
$regRoots = @(
  "HKCU:\Software\Google\Chrome\NativeMessagingHosts",
  "HKCU:\Software\Microsoft\Edge\NativeMessagingHosts",
  "HKCU:\Software\Chromium\NativeMessagingHosts",
  "HKCU:\Software\BraveSoftware\Brave-Browser\NativeMessagingHosts"
)

if ($Uninstall) {
  foreach ($r in $regRoots) { $k = Join-Path $r $name; if (Test-Path $k) { Remove-Item $k -Recurse; Write-Host "Removed $k" } }
  exit 0
}

if (-not (Test-Path $py)) { throw "Virtualenv not found ($py) - run .\install.cmd first." }

# 1) .bat wrapper Chrome will launch (path in the manifest must be an executable or .bat)
@"
@echo off
"$py" -u "$(Join-Path $server 'polarnik_host.py')" %*
"@ | Set-Content -Path $bat -Encoding ASCII

# 2) host manifest with absolute path and the extension id
(Get-Content (Join-Path $hostDir "$name.json.template") -Raw) `
  -replace "__HOST_PATH__", ($bat -replace "\\", "\\") `
  -replace "__EXTENSION_ID__", $extId | Set-Content -Path $manifest -Encoding UTF8

# 3) registry: default value of the key = path to the manifest
foreach ($r in $regRoots) {
  $k = Join-Path $r $name
  New-Item -Path $k -Force | Out-Null
  Set-ItemProperty -Path $k -Name "(default)" -Value $manifest
}
Write-Host "Registered native messaging host '$name' for extension $extId"
Write-Host "Manifest: $manifest"
Write-Host "Reload the extension in chrome://extensions (its id must be $extId)."
