@echo off
chcp 65001 >nul
title Cap nhat ViDub
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if exist ".venv\Scripts\python.exe" (set PY=.venv\Scripts\python.exe) else (set PY=python)
%PY% update.py %*
echo.
pause
