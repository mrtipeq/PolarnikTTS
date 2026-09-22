# Starts the PolarnikTTS engine server using server\.venv and server\config.yaml.
param([string]$BindHost = "", [int]$Port = 0)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$server = Join-Path $root "server"
$vpy = Join-Path $server ".venv\Scripts\python.exe"
if (-not (Test-Path $vpy)) { Write-Error "Virtualenv not found - run .\install.ps1 first."; exit 1 }

$argList = @("-m", "polarnik_server", "--config", (Join-Path $server "config.yaml"))
if ($BindHost) { $argList += @("--host", $BindHost) }
if ($Port) { $argList += @("--port", $Port) }

Push-Location $server
try { & $vpy @argList } finally { Pop-Location }
