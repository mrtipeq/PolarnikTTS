@echo off
rem Updates this PolarnikTTS installation from GitHub (keeps config, voices, models, GPU envs).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update.ps1" %*
pause
