# -*- coding: utf-8 -*-
"""
核心工具模块：路径、配置、网络检测、管理员权限、防火墙、端口占用、外部程序发现
由 GUI 与 DNS 引擎共同调用（原 common.py / 各 bat 的功能整合）。
"""
import os
import re
import sys
import glob
import socket
import shutil
import subprocess

# 打包成无控制台 GUI 后，避免子进程闪黑窗
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ---------------------------------------------------------------------------
# 路径解析：开发态与 PyInstaller 打包态都能定位到工具目录（含 mediamtx、配置文件）
# ---------------------------------------------------------------------------
def _bundle_dir():
    """只读资源（图标/qss/捆绑程序）所在目录：打包后为 _MEIPASS，开发时为源码目录。"""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(*parts):
    return os.path.join(_bundle_dir(), *parts)


def tool_base_dir():
    """
    可写工具目录：mediamtx/mediamtx.exe、推流配置.txt、stream_urls.txt 所在位置。
    打包后 EXE 放在工具根目录；开发时源码在 gui_src 子目录，工具根目录是上一级。
    """
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(os.path.dirname(os.path.abspath(sys.executable)))
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(here)
    candidates.append(os.path.dirname(here))
    for c in candidates:
        if os.path.isfile(os.path.join(c, "mediamtx", "mediamtx.exe")):
            return c
    # 找不到 mediamtx 时，优先用 EXE 所在目录（开发态回退到源码目录）
    return candidates[0]


BASE_DIR = tool_base_dir()
CONFIG_PATH = os.path.join(BASE_DIR, "推流配置.txt")
MEDIAMTX_DIR = os.path.join(BASE_DIR, "mediamtx")
MEDIAMTX_EXE = os.path.join(MEDIAMTX_DIR, "mediamtx.exe")
STREAM_URLS_FILE = os.path.join(BASE_DIR, "stream_urls.txt")


# ---------------------------------------------------------------------------
# 配置读写（兼容 GBK/UTF-8 记事本另存；保存时回写一份带注释的规范文件）
# ---------------------------------------------------------------------------
def read_text_auto(path):
    if not os.path.exists(path):
        return ""
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8-sig", "gbk", "utf-16", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="ignore")


DEFAULT_CONFIG = {
    "网关IP": "",
    "上游DNS": "自动",
    "自定义推流地址": "",
    "抖音推流地址": "",
    "抖音推流码": "",
    "B站推流地址": "",
    "B站推流码": "",
    "重编码": "否",
    "主题": "黑夜",
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    text = read_text_auto(CONFIG_PATH)
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("；") or line.startswith(";"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            cfg[key.strip()] = val.strip()
    return cfg


_CONFIG_TEMPLATE = """# ============================================================
#  PS5 直播推流配置文件（由图形界面自动生成，也可手动编辑）
#  说明：等号后面填内容，# 开头是注释；改完保存即可
# ============================================================

# PS5 网关 IP（电脑连接 PS5 那块网卡的 IP）。留空=自动检测（推荐）
网关IP={网关IP}

# 上游 DNS：填“自动”会逐个测速并选最快的；若 PS5 断网可改成加速器 DNS（如 8.8.8.1）
上游DNS={上游DNS}

# ---------- 方式一：转推到你自己的 RTMP 后台（推荐）----------
# 把后台给的“完整推流URL”整串填在等号后面（必须 rtmp:// 开头），不要拆分
自定义推流地址={自定义推流地址}

# ---------- 方式二：直接转推平台（用不到就留空）----------
抖音推流地址={抖音推流地址}
抖音推流码={抖音推流码}
B站推流地址={B站推流地址}
B站推流码={B站推流码}

# 编码：否=直接转发(省CPU，默认)；后台黑屏/拉不到流时改成 是
重编码={重编码}

# 界面主题：黑夜 或 白天（也可在主界面右上角一键切换）
主题={主题}
"""


def save_config(cfg: dict):
    merged = dict(DEFAULT_CONFIG)
    merged.update({k: v for k, v in cfg.items() if k in DEFAULT_CONFIG})
    os.makedirs(BASE_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(_CONFIG_TEMPLATE.format(**merged))
    return CONFIG_PATH


# ---------------------------------------------------------------------------
# 网络检测（移植自 common.py，逻辑保持一致）
# ---------------------------------------------------------------------------
def get_all_ipv4():
    try:
        out = subprocess.run(["ipconfig"], capture_output=True,
                             creationflags=NO_WINDOW).stdout
        text = out.decode("gbk", errors="ignore")
    except Exception:
        return []
    ips = re.findall(
        r"IPv4\s*(?:地址|Address)[^:\d]*:?\s*(\d+\.\d+\.\d+\.\d+)", text
    )
    seen, result = set(), []
    for ip in ips:
        if ip not in seen:
            seen.add(ip)
            result.append(ip)
    return result


def get_main_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("223.5.5.5", 53))
        return s.getsockname()[0]
    except Exception:
        return None
    finally:
        s.close()


def _is_private_accelerator_ip(ip):
    try:
        a, b = int(ip.split(".")[0]), int(ip.split(".")[1])
    except Exception:
        return 0
    if a == 172 and 16 <= b <= 31:
        return 3
    if a == 10:
        return 2
    if a == 192 and b == 168:
        return 1
    return 0


def detect_gateway_ip(manual=""):
    """返回 (ip, mode)；mode ∈ direct / router / manual，找不到返回 (None, '')。"""
    manual = (manual or "").strip()
    if manual:
        return manual, "manual"

    all_ips = get_all_ipv4()
    valid = [ip for ip in all_ips
             if not ip.startswith("127.") and not ip.startswith("169.254.")]
    if not valid:
        return None, ""

    acc = [ip for ip in valid if _is_private_accelerator_ip(ip) == 3]
    if acc:
        return acc[0], "direct"

    main_ip = get_main_ip()
    if main_ip and main_ip in valid and _is_private_accelerator_ip(main_ip) > 0:
        return main_ip, "router"

    rest = [ip for ip in valid if _is_private_accelerator_ip(ip) > 0]
    rest.sort(key=lambda x: _is_private_accelerator_ip(x), reverse=True)
    if rest:
        return rest[0], "router"
    return valid[0], "router"


# ---------------------------------------------------------------------------
# 管理员权限
# ---------------------------------------------------------------------------
def is_admin():
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 防火墙规则（netsh），返回 [(规则名, 是否成功, 信息)]
# ---------------------------------------------------------------------------
FIREWALL_RULES = [
    ("PS5Live_DNS", "UDP", 53),
    ("PS5Live_DNS_TCP", "TCP", 53),
    ("PS5Live_RTMP", "TCP", 1935),
]


def _run(cmd, timeout=15):
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout,
                           creationflags=NO_WINDOW)
        out = (p.stdout or b"").decode("gbk", errors="ignore") + \
              (p.stderr or b"").decode("gbk", errors="ignore")
        return p.returncode, out
    except Exception as e:
        return -1, str(e)


def add_firewall_rules():
    results = []
    for name, proto, port in FIREWALL_RULES:
        _run(["netsh", "advfirewall", "firewall", "delete", "rule",
              "name=" + name])
        rc, out = _run(["netsh", "advfirewall", "firewall", "add", "rule",
                        "name=" + name, "dir=in", "action=allow",
                        "protocol=" + proto, "localport=" + str(port),
                        "profile=any"])
        ok = rc == 0 and "确定" in out or rc == 0 and "Ok" in out
        results.append((name, proto, port, bool(ok), out.strip()[:120]))
    return results


def remove_firewall_rules():
    results = []
    for name, proto, port in FIREWALL_RULES:
        rc, out = _run(["netsh", "advfirewall", "firewall", "delete", "rule",
                        "name=" + name])
        results.append((name, bool(rc == 0)))
    return results


# ---------------------------------------------------------------------------
# 端口占用检测：返回占用进程 [(pid, 进程名, 地址)]，未占用返回 []
# ---------------------------------------------------------------------------
def _pid_to_name(pid):
    rc, out = _run(["tasklist", "/FI", "PID eq " + str(pid), "/FO", "CSV",
                    "/NH"])
    m = re.search(r'"([^"]+\.exe)"', out)
    return m.group(1) if m else ("PID " + str(pid))


def find_port_owners(port, proto="tcp"):
    """proto: 'tcp' 或 'udp'。返回 [(pid, 进程名, 本地地址, 协议)]。"""
    rc, out = _run(["netstat", "-ano", "-p", proto])
    owners = []
    seen = set()
    for line in out.splitlines():
        parts = line.split()
        if not parts:
            continue
        # 形如  TCP   0.0.0.0:53   0.0.0.0:0   LISTENING   1234
        # UDP 无状态列：  UDP   0.0.0.0:53   *:*   1234
        local = None
        pid = None
        for token in parts:
            if ":" in token and re.search(r"[:.]" + str(port) + r"\s*$", token) \
                    and local is None:
                local = token
        if local is None:
            continue
        m = re.search(r"[:.]" + str(port) + r"$", local)
        if not m:
            continue
        try:
            pid = int(parts[-1])
        except Exception:
            continue
        if pid in (0, 4) and proto == "udp":
            # 系统内核占用（如 DNS Client/DNS 服务）也报出来
            name = "系统服务 (svchost/Services)"
        else:
            name = _pid_to_name(pid)
        key = (pid, local)
        if key not in seen:
            seen.add(key)
            owners.append((pid, name, local, proto.upper()))
    return owners


def port_listeners(port, protos=("tcp", "udp")):
    res = []
    for p in protos:
        res.extend(find_port_owners(port, p))
    return res


# ---------------------------------------------------------------------------
# 外部程序发现
# ---------------------------------------------------------------------------
def find_ffmpeg():
    """优先本地捆绑，其次 PATH，再扫常见安装位置。返回 exe 路径或 None。"""
    candidates = [
        os.path.join(BASE_DIR, "ffmpeg", "ffmpeg.exe"),
        os.path.join(BASE_DIR, "bin", "ffmpeg.exe"),
        resource_path("bin", "ffmpeg.exe"),
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    found = shutil.which("ffmpeg")
    if found:
        return found
    patterns = [
        os.path.expandvars(
            r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*"
            r"\**\bin\ffmpeg.exe"),
        r"C:\Program Files\ffmpeg*\**\bin\ffmpeg.exe",
        r"C:\ffmpeg*\**\bin\ffmpeg.exe",
    ]
    for pat in patterns:
        hits = glob.glob(pat, recursive=True)
        if hits:
            return hits[0]
    return None


def find_mediamtx():
    return MEDIAMTX_EXE if os.path.isfile(MEDIAMTX_EXE) else None


def open_in_explorer(path):
    try:
        if os.path.isfile(path):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            subprocess.Popen(["explorer", os.path.normpath(path)])
        return True
    except Exception:
        return False


def open_url(url):
    try:
        os.startfile(url)
        return True
    except Exception:
        try:
            import webbrowser
            webbrowser.open(url)
            return True
        except Exception:
            return False
