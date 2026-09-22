@echo off
chcp 936 >nul 2>&1
title PS5-Live-Stop
cd /d "%~dp0"

echo ========================================================
echo            停止 PS5 直播相关进程
echo ========================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_all.ps1"

echo.
echo 已停止本工具启动的全部进程（防火墙规则保留，下次启动更快）。
echo 若要彻底清除防火墙规则并删除工具，请运行“一键撤回.bat”。
echo ========================================================
echo.
pause
