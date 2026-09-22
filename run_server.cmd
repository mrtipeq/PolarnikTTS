@echo off
rem Starts the PolarnikTTS engine server regardless of the PowerShell execution policy.
rem Usage: run_server.cmd [-BindHost 0.0.0.0] [-Port 8765]
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_server.ps1" %*
if errorlevel 1 pause
