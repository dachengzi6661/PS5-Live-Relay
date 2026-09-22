@echo off
chcp 936 >nul 2>&1
title PS5-MediaMTX
cd /d "%~dp0mediamtx"
echo ========================================================
echo   MediaMTX 本地 RTMP 服务器（本窗口请勿关闭）
echo   看到 listener opened on :1935 即正常
echo ========================================================
echo.
mediamtx.exe
echo.
echo MediaMTX 已退出。如非主动关闭，请把本窗口截图反馈。
pause
