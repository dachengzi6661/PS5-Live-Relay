# source/ — 源码说明

本目录是 PS5 直播推流助手的两套实现。**普通用户请直接用 `release/` 里的成品**，无需本目录。

```
source/
├── README.md              本文件
├── requirements.txt       依赖清单
│
├── 【命令行版】不依赖图形界面，直接双击 .bat 即可
│   ├── common.py          控制台编码统一、配置读取、网卡/网关检测
│   ├── dns_proxy.py       DNS 劫持服务（dnslib 实现）
│   ├── relay.py           ffmpeg 转推管理
│   ├── monitor.py         查找在线流、拼装拉流地址
│   ├── ①一键启动.bat       放行防火墙 + 启动 MediaMTX 和 DNS（需管理员）
│   ├── ②转推*.bat          转推到自定义 RTMP 后台 / 抖音 / B站
│   ├── ③一键停止.bat       停止全部服务
│   ├── ④监看*.bat          打开播放页并拼好 RTMP / HLS 拉流地址
│   ├── start_dns.bat / start_mediamtx.bat   被 ① 调用的两个子脚本
│   ├── stop_all.ps1       停进程
│   ├── uninstall.ps1      删防火墙规则
│   ├── 一键撤回.bat        停止 + 删防火墙规则（含自删除）
│   └── 推流配置.txt        配置文件（与图形界面共用同一份格式）
│
└── gui_src/               【图形界面版】PySide6 (Qt6)
    ├── app.py             入口：启动动画 → 主窗口；单实例保护
    ├── core.py            路径解析（开发态 / 打包态）、配置读写、网卡检测、ffmpeg 查找
    ├── theme.py           主题配色与 QSS（白天 / 黑夜双主题）
    ├── widgets.py         自绘控件：胶囊按钮、分段导航、开关、进度条、日志台等
    ├── main_window.py     主窗口 + 总览 / 监看 / 设置 / 诊断 / 日志 五个页面
    ├── splash.py          启动动画
    ├── dns_engine.py      DNS 劫持引擎（基于 dnslib，Qt 信号回传事件）
    ├── workers.py         MediaMTX 进程管理与 ffmpeg 转推管理
    ├── diagnostics.py     5 关状态机 + 诊断文案（按设备归因）
    ├── wineffects.py      Windows 亚克力特效辅助（当前版本未启用，保留备用）
    ├── make_assets.py     用 Pillow 生成 app.ico / app.png / splash.png
    ├── build.py           一键打包：生成资源 → PyInstaller 单文件 → 复制产物
    ├── build.ps1          打包快捷入口（PowerShell）
    └── assets/            图标与启动图
```

## 运行环境

```bash
pip install -r requirements.txt
```

- 图形界面版需要 **PySide6**；命令行版只需要 **dnslib**。
- 打包（`build.py`）额外需要 **PyInstaller** 与 **Pillow**。
- 转推功能需要系统已安装 **ffmpeg**（在 `PATH` 中，或放在程序目录的 `ffmpeg\` 或 `bin\` 下）。

## 运行

```bash
# 图形界面版
cd gui_src
python app.py

# 打包成单文件 EXE（产物在 ./dist/ 并自动复制到 source/）
python build.py
```

## 注意

1. **`mediamtx/` 不在源码目录里**。开发态运行时，`core.tool_base_dir()` 会在 `source/` 下寻找 `mediamtx\mediamtx.exe`。
   想跑通收流，请把 `../release/mediamtx/` 整个复制到 `source/` 目录下。
2. **批处理脚本里的 Python 解释器**默认取 `PATH` 中的 `python`，取不到时退化为 `py` 启动器。
   若你的 Python 不在 `PATH`，请把脚本里的 `set "PYEXE=python"` 改成你的 `python.exe` 完整路径。
3. **打包好的 EXE 无法在未提权时自测**：`--uac-admin` 会让它启动即弹 UAC，属正常现象。
4. `stream_urls.txt` 是运行时生成的本机会话文件（`127.0.0.1` 临时拉流地址），已被 `.gitignore` 忽略。
