@echo off
rem Installs (or with -Uninstall removes) the Windows autostart of the PolarnikTTS server.
rem Usage: autostart.cmd [-Uninstall] [-Status]
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0autostart.ps1" %*
if errorlevel 1 pause
