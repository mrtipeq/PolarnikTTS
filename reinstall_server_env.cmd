@echo off
rem Wipes server\.venv and reinstalls the server (edge-tts + piper). Isolated engine envs
rem (server\envs\*) and downloaded models are kept.
setlocal
cd /d "%~dp0"
call stop_server.cmd >nul 2>&1
if exist "server\.venv" (
  echo Removing server\.venv ...
  rmdir /s /q "server\.venv"
)
call install.cmd %*
