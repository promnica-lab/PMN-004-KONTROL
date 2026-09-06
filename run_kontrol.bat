@echo off
cd /d "%~dp0"
python kontrol.py
if errorlevel 1 (
  echo.
  echo KONTROL failed to start.
  pause
)
