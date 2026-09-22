@echo off
rem Builds Chrome Web Store zips into dist\. Optional: pass the path to the private key (.pem).
rem Usage: pack_extension.cmd [D:\path\to\PolarnikTTS_extension_key.pem]
setlocal
cd /d "%~dp0"
set PY=server\.venv\Scripts\python.exe
if not exist "%PY%" set PY=python
if "%~1"=="" (
  "%PY%" scripts\pack_extension.py
) else (
  "%PY%" scripts\pack_extension.py --key "%~1"
)
pause
