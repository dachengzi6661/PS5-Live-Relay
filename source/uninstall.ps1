# -*- coding: utf-8 -*-
# 一键撤回：删除防火墙规则，并在脚本退出后自删除整个工具文件夹
$ErrorActionPreference = 'SilentlyContinue'
$dir = $PSScriptRoot

Write-Host "[1/2] 删除防火墙规则 ..."
netsh advfirewall firewall delete rule name="PS5Live_DNS"     | Out-Null
netsh advfirewall firewall delete rule name="PS5Live_DNS_TCP" | Out-Null
netsh advfirewall firewall delete rule name="PS5Live_RTMP"    | Out-Null
Write-Host "      防火墙规则已删除。"

Write-Host "[2/2] 安排自删除任务（3 秒后删除工具文件夹）..."
# 启动独立隐藏进程，等当前脚本和窗口退出后再删除目录
$inner = "Start-Sleep -Seconds 3; Remove-Item -LiteralPath '$dir' -Recurse -Force -ErrorAction SilentlyContinue"
Start-Process powershell -WindowStyle Hidden -ArgumentList @('-NoProfile','-Command',$inner)

Write-Host "完成。"
