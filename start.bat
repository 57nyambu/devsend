@echo off
echo ========================================
echo        DevSend - Quick Start
echo ========================================
echo.

REM Check if virtual environment exists
if not exist "venv\" (
    echo Creating virtual environment...
    python -m venv venv
    echo.
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Check if requirements are installed
pip show fastapi >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r requirements.txt
    echo.
)

REM Check if .env exists
if not exist ".env" (
    echo Creating .env file from template...
    copy .env.example .env
    echo.
    echo IMPORTANT: Edit .env file with your settings!
    echo.
)

echo Starting DevSend...
echo.
echo Access the application at: http://localhost:8000
echo Default credentials: admin / changeme
echo.
echo Press Ctrl+C to stop the server
echo.

python -m devsend.main
