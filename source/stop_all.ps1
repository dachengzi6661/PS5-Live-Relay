# -*- coding: utf-8 -*-
# 停止本工具启动的全部进程（精确匹配，不误伤其他 Python）
$ErrorActionPreference = 'SilentlyContinue'

Write-Host "[1/3] 停止 MediaMTX ..."
Stop-Process -Name mediamtx -Force

Write-Host "[2/3] 停止 DNS劫持 / 转推脚本（仅匹配本工具，不影响其他Python）..."
$pyProcs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'dns_proxy|relay' }
if ($pyProcs) {
    foreach ($pr in $pyProcs) {
        Write-Host ("      结束 Python PID=" + $pr.ProcessId)
        Stop-Process -Id $pr.ProcessId -Force
    }
} else {
    Write-Host "      没有正在运行的本工具 Python 脚本。"
}

Write-Host "[3/3] 停止 ffmpeg 转推 ..."
Stop-Process -Name ffmpeg -Force

Write-Host "完成。"
