@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 goto error
)

call ".venv\Scripts\activate.bat"

echo Installing requirements...
python -m pip install --upgrade pip
if errorlevel 1 goto error
python -m pip install -r requirements.txt
if errorlevel 1 goto error

echo Running database migrations...
python -m alembic upgrade head
if errorlevel 1 goto error

echo.
echo System is starting...
echo Open: http://127.0.0.1:8000
echo Login: admin@saeed-law.test / Admin12345
echo.

start "" powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0scripts\open-browser.ps1"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

if errorlevel 1 goto error
endlocal
exit /b 0

:error
echo.
echo Failed to start the system. Check the error messages above.
echo If port 8000 is already in use, close the old server window and run this file again.
pause
endlocal
exit /b 1
