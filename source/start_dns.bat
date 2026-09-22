@echo off
chcp 936 >nul 2>&1
title PS5-DNS-Server
cd /d "%~dp0"
set PYTHONIOENCODING=gbk
set PYTHONUTF8=0
set "PYEXE=python"
REM Prefer 'python' on PATH, fall back to the 'py' launcher.
where python >nul 2>&1
if errorlevel 1 set "PYEXE=py"
"%PYEXE%" dns_proxy.py
