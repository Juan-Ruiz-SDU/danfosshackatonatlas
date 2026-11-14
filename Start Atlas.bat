@echo off
rem Double-click to start the Atlas app. It opens in your browser.
cd /d "%~dp0"
python --version >nul 2>nul
if errorlevel 1 (
  echo Python is not installed.
  echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH",
  echo then double-click this file again.
  pause
  exit /b 1
)
python -c "import fpdf, pypdf" >nul 2>nul
if errorlevel 1 (
  echo First start: installing the PDF tools...
  python -m pip install -r requirements.txt
)
python Run.py app
pause
