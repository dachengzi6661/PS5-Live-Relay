@echo off
chcp 936 >nul 2>&1
title PS5-Live-Uninstall
cd /d "%~dp0"

REM ===== 自动申请管理员权限（删防火墙规则需要）=====
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo ========================================================
echo          一键撤回 / 卸载 PS5 直播推流工具
echo ========================================================
echo.
echo  将执行以下操作：
echo    1. 停止 MediaMTX / DNS劫持 / ffmpeg 等相关进程
echo    2. 删除本工具添加的 3 条防火墙规则
echo    3. 删除桌面上整个“PS5直播推流工具”文件夹（含本脚本）
echo.
echo  注意：PS5 主机上的 DNS 设置需要你手动改回（见最后提示）。
echo        “推流配置.txt”里的推流码也会随文件夹一起删除。
echo.
choice /c YN /m "确定要继续撤回吗（Y=确定，N=取消）"
if errorlevel 2 (
    echo 已取消，未做任何改动。
    pause
    exit /b
)

echo.
echo [1/2] 停止相关进程 ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_all.ps1"

echo.
echo [2/2] 删除防火墙规则并安排自删除 ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1"

echo.
echo ========================================================
echo  撤回完成！工具文件夹将在本窗口关闭 3 秒后自动删除。
echo.
echo  【还需你手动操作】把 PS5 的 DNS 改回加速器默认值：
echo    PS5 - 设置 - 网络 - 高级设置 - DNS：
echo    首选 DNS 改回加速器给的地址（AK 默认 8.8.8.1），
echo    或直接设为“自动获取”，其余 IP/网关保持不变。
echo.
echo  桌面上的“PS5直播懒人教程.md”不会被自动删除，如不需要可手动删。
echo ========================================================
echo.
timeout /t 4 >nul
exit /b
