@echo off
title Cai dat ViDub
cd /d "%~dp0"
echo ===============================================
echo   CAI DAT VIDUB - Phu de + long tieng video
echo   Can internet. Mat khoang 10-20 phut lan dau.
echo   Dung tat cua so nay cho toi khi bao XONG.
echo ===============================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
if errorlevel 1 (
  echo.
  echo  *** CAI DAT BI LOI. Chup man hinh cua so nay gui nguoi gui tool. ***
  echo  Co the bam dup Cai_dat.bat lan nua de thu lai - cac buoc da xong se duoc bo qua.
)
echo.
pause
