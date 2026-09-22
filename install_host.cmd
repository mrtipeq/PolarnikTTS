@echo off
rem Registers the native messaging host that lets the extension start the server on demand.
rem Usage: install_host.cmd [-Uninstall]
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_host.ps1" %*
if errorlevel 1 pause
