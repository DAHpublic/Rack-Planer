@echo off
REM Baut dist\Rack-Planer_v<Version>.exe (Windows); aeltere EXE-Dateien bleiben erhalten. Voraussetzung: Python 3.10+ von python.org
REM (bei der Installation "Add python.exe to PATH" anhaken).
setlocal
cd /d "%~dp0"

where py >nul 2>nul && (set PY=py -3) || (set PY=python)

echo [1/3] Virtuelle Umgebung anlegen ...
%PY% -m venv .venv || goto :error
call .venv\Scripts\activate.bat

echo [2/3] Abhaengigkeiten installieren ...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt pyinstaller || goto :error

echo [3/3] EXE bauen ...
python build.py || goto :error
pause
exit /b 0

:error
echo.
echo Build fehlgeschlagen.
pause
exit /b 1
