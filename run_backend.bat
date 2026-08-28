@echo off
cd /d "%~dp0backend"
if not exist .venv\Scripts\python.exe (
  echo Backend virtual environment not found. Run setup.bat first.
  pause
  exit /b 1
)
if not exist .env (
  echo MongoDB configuration file backend\.env is missing.
  echo Run setup.bat, then edit backend\.env with the shared MongoDB Atlas connection string.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m uvicorn app:app --host 127.0.0.1 --port 8000
