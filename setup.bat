@echo off
setlocal
cd /d "%~dp0"
echo ========================================
echo SolarCharge first-time setup
echo ========================================
echo.
if not exist backend\.env (
  copy /Y backend\.env.example backend\.env >nul
  echo IMPORTANT: backend\.env was created from .env.example.
  echo Edit it and add the shared MongoDB Atlas connection string before running the website.
  echo.
)
echo [1/2] Installing Python backend dependencies...
cd backend
if not exist .venv (
  python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Backend dependency installation failed.
  pause
  exit /b 1
)
cd ..
echo.
echo [2/2] Installing React frontend dependencies...
call npm install
if errorlevel 1 (
  echo.
  echo Frontend dependency installation failed.
  pause
  exit /b 1
)
echo.
echo Setup complete.
echo IMPORTANT: the optimizer also requires a valid Gurobi license on this computer.
pause
