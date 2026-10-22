@echo off
title Telecom Churn Prediction Launcher
cd /d "%~dp0"
echo ========================================================
echo  Telecom Customer Churn Prediction & Risk Analysis
echo ========================================================
echo.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run_app.py
) else (
    python run_app.py
)
pause
