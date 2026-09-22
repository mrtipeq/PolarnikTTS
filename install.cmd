@echo off
rem Runs install.ps1 regardless of the PowerShell execution policy.
rem Usage: install.cmd [-Extras edge,piper,chatterbox] [-Cuda cu128]
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
if errorlevel 1 (
  echo.
  echo Installation failed - see the messages above.
  pause
)
