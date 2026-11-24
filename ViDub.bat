@echo off
chcp 65001 >nul
title ViDub - DUNG TAT CUA SO NAY khi dang dung app
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set PY=
if exist ".venv\Scripts\python.exe" set PY=.venv\Scripts\python.exe
if not defined PY if exist "E:\WorkSpace\Python\InstallNew\python.exe" set PY=E:\WorkSpace\Python\InstallNew\python.exe
if not defined PY (
  echo ViDub chua duoc cai. Bam dup file Cai_dat.bat truoc.
  pause
  exit /b 1
)
echo ===============================================
echo   ViDub dang chay tai http://localhost:7860
echo   Giu cua so nay mo trong luc dung app.
echo ===============================================
"%PY%" app.py
echo.
echo ViDub da dung. Neu co loi o tren, chup man hinh gui nguoi gui tool.
pause
