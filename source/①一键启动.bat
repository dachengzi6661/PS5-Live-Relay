@echo off
chcp 936 >nul 2>&1
title PS5-Live-Start
cd /d "%~dp0"

REM ===== 自动申请管理员权限 =====
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo 正在申请管理员权限，请在弹窗中点“是”...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo ========================================================
echo            PS5 直播推流 - 一键启动
echo ========================================================
echo.

REM ===== 配置防火墙放行（先删后建，保证幂等），并逐条报告结果 =====
echo [1/3] 配置防火墙（放行 PS5 到本机的 DNS 53 与 RTMP 1935）...
set FWFAIL=0
netsh advfirewall firewall delete rule name="PS5Live_DNS"      >nul 2>&1
netsh advfirewall firewall delete rule name="PS5Live_DNS_TCP"  >nul 2>&1
netsh advfirewall firewall delete rule name="PS5Live_RTMP"     >nul 2>&1

netsh advfirewall firewall add rule name="PS5Live_DNS"     dir=in action=allow protocol=UDP localport=53   profile=any >nul 2>&1
if %errorlevel%==0 (echo       [OK] UDP 53 已放行) else (echo       [失败] UDP 53 未放行 & set FWFAIL=1)
netsh advfirewall firewall add rule name="PS5Live_DNS_TCP" dir=in action=allow protocol=TCP localport=53   profile=any >nul 2>&1
if %errorlevel%==0 (echo       [OK] TCP 53 已放行) else (echo       [失败] TCP 53 未放行 & set FWFAIL=1)
netsh advfirewall firewall add rule name="PS5Live_RTMP"    dir=in action=allow protocol=TCP localport=1935 profile=any >nul 2>&1
if %errorlevel%==0 (echo       [OK] TCP 1935 已放行) else (echo       [失败] TCP 1935 未放行 & set FWFAIL=1)

if "%FWFAIL%"=="1" (
    echo       [警告] 有防火墙规则没建成，PS5 可能连不上本服务。
    echo              请确认 UAC 弹窗点了“是”；可关掉杀毒/防火墙后重试。
)
echo.

REM ===== 启动两个服务（各自独立窗口）=====
echo [2/3] 启动本地 RTMP 服务器 MediaMTX ...
start "MediaMTX" cmd /k "%~dp0start_mediamtx.bat"
timeout /t 2 >nul

echo [3/3] 启动 DNS 劫持服务（会自动检测网关并测试上游DNS）...
start "DNS劫持服务" cmd /k "%~dp0start_dns.bat"
timeout /t 2 >nul

echo.
echo ========================================================
echo  已弹出两个新窗口，请重点看“DNS劫持服务”窗口：
echo    1) 必须出现 [可用] 的上游DNS 和 “已在 0.0.0.0:53 监听”
echo       —— 若全部[不通]，PS5会断网，按该窗口提示排查
echo    2) 记住它显示的“首选DNS”地址（即PS5网关IP）
echo.
echo  接下来：
echo    - PS5 网络设置里，首选DNS 填上面那个网关IP，备选留空
echo    - PS5 对 Twitch 开始直播，DNS窗口出现 [劫持] 行
echo    - 双击 “②转推RTMP后台.bat”（或抖音/B站）
echo    - 想先看画面就双击 “④监看画面.bat”
echo.
echo  本窗口可关闭；停止全部双击 “③一键停止.bat”
echo ========================================================
echo.
pause