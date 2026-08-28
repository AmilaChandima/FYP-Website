@echo off
cd /d "%~dp0"
start "SolarCharge Python API" cmd /k call "%~dp0run_backend.bat"
start "SolarCharge React Web" cmd /k call "%~dp0run_frontend.bat"
echo Customer site: http://localhost:5173
echo Admin login  : http://localhost:5173/admin
