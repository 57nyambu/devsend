# DevSend Quick Start Script

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "       DevSend - Quick Start" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if virtual environment exists
if (-not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv venv
    Write-Host ""
}

# Activate virtual environment
& ".\venv\Scripts\Activate.ps1"

# Check if requirements are installed
$fastapi = pip show fastapi 2>$null
if (-not $fastapi) {
    Write-Host "Installing dependencies..." -ForegroundColor Yellow
    pip install -r requirements.txt
    Write-Host ""
}

# Check if .env exists
if (-not (Test-Path ".env")) {
    Write-Host "Creating .env file from template..." -ForegroundColor Yellow
    Copy-Item .env.example .env
    Write-Host ""
    Write-Host "IMPORTANT: Edit .env file with your settings!" -ForegroundColor Red
    Write-Host ""
}

Write-Host "Starting DevSend..." -ForegroundColor Green
Write-Host ""
Write-Host "Access the application at: " -NoNewline
Write-Host "http://localhost:8000" -ForegroundColor Green
Write-Host "Default credentials: " -NoNewline
Write-Host "admin / changeme" -ForegroundColor Yellow
Write-Host ""
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Gray
Write-Host ""

python -m devsend.main
