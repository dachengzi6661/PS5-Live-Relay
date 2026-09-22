# -*- coding: utf-8 -*-
"""
公共模块：控制台编码、配置读取、网卡/网关自动检测
被 dns_proxy.py 和 relay.py 共同使用
"""
import os
import re
import sys
import socket
import subprocess

# ---------- 统一控制台输出编码，彻底防止中文乱码 ----------
def setup_utf8():
    """
    启动脚本(bat)已 chcp 936 并 set PYTHONUTF8=0。这里再无条件把控制台
    代码页强制设为 GBK(936)、把 Python 输出强制设为 gbk，做到 bat 与 python
    完全对齐——不依赖系统默认代码页、不依赖是否继承了 PYTHONUTF8，从根上杜绝乱码。
    errors='replace' 保证任何生僻字符都不会让脚本崩溃。
    """
    enc = "gbk"
    try:
        import ctypes
        k = ctypes.windll.kernel32
        k.SetConsoleOutputCP(936)
        k.SetConsoleCP(936)
        cp = k.GetConsoleOutputCP()
        # 正常应得 936；极端情况下设不回去才退回 utf-8
        if cp == 65001:
            enc = "utf-8"
        else:
            enc = "gbk"
    except Exception:
        enc = "gbk"
    try:
        os.environ["PYTHONUTF8"] = "0"
    except Exception:
        pass
    for stream_name in ("stdout", "stderr"):
        try:
            getattr(sys, stream_name).reconfigure(encoding=enc, errors="replace")
        except Exception:
            try:
                getattr(sys, stream_name).reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

# ---------- 工具目录 / 配置文件路径 ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "推流配置.txt")

# ---------- 以兼容编码读取文本（兼容记事本另存为 ANSI/GBK 或 UTF-8 的情况）----------
def read_text_auto(path):
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8-sig", "gbk", "utf-16", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="ignore")

# ---------- 读取配置（键=值，# 开头为注释） ----------
def load_config():
    cfg = {}
    if not os.path.exists(CONFIG_PATH):
        return cfg
    text = read_text_auto(CONFIG_PATH)
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("；"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            cfg[key.strip()] = val.strip()
    return cfg

# ---------- 获取电脑上所有 IPv4 地址（解析 ipconfig，兼容中英文系统） ----------
def get_all_ipv4():
    try:
        out = subprocess.run(["ipconfig"], capture_output=True).stdout
        text = out.decode("gbk", errors="ignore")
    except Exception:
        return []
    # 兼容“IPv4 地址 . . . : x”和“IPv4 Address . . : x”
    ips = re.findall(r"IPv4\s*(?:地址|Address)[^:\d]*:?\s*(\d+\.\d+\.\d+\.\d+)", text)
    # 去重并保持顺序
    seen, result = set(), []
    for ip in ips:
        if ip not in seen:
            seen.add(ip)
            result.append(ip)
    return result

# ---------- 获取“默认上网网卡”的 IP（连外网走的那块网卡） ----------
def get_main_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("223.5.5.5", 53))
        return s.getsockname()[0]
    except Exception:
        return None
    finally:
        s.close()

# ---------- 判断是否为私有/加速器网段 ----------
def _is_private_accelerator_ip(ip):
    try:
        a, b = int(ip.split(".")[0]), int(ip.split(".")[1])
    except Exception:
        return False
    if a == 172 and 16 <= b <= 31:   # 172.16.0.0/12，AK 等加速器常用
        return 3
    if a == 10:                      # 10.0.0.0/8
        return 2
    if a == 192 and b == 168:        # 192.168.0.0/16
        return 1
    return 0

# ---------- 自动检测“PS5 该把首选DNS填成的电脑IP”，兼容两种加速拓扑 ----------
def detect_gateway_ip(manual=""):
    """
    返回 (ip, mode)；找不到返回 (None, "")。
    模式一 direct ：PS5 网线直连电脑、电脑当网关（加速器虚拟网段 172.16-31）
    模式二 router ：PS5 与电脑连同一个路由器（局域网加速），用电脑上网网卡IP
    manual：配置里手动指定则直接用。
    """
    manual = (manual or "").strip()
    if manual:
        return manual, "manual"

    all_ips = get_all_ipv4()
    valid = [ip for ip in all_ips
             if not ip.startswith("127.") and not ip.startswith("169.254.")]
    if not valid:
        return None, ""

    # 模式一：加速器虚拟网段 172.16-31（PS5 直连电脑），最高优先
    acc = [ip for ip in valid if _is_private_accelerator_ip(ip) == 3]
    if acc:
        return acc[0], "direct"

    # 模式二：局域网模式，PS5 与电脑同一路由器 —— 直接用默认上网网卡IP
    main_ip = get_main_ip()
    if main_ip and main_ip in valid and _is_private_accelerator_ip(main_ip) > 0:
        return main_ip, "router"

    # 兜底：其余私有地址按 10.x > 192.168 排序
    rest = [ip for ip in valid if _is_private_accelerator_ip(ip) > 0]
    rest.sort(key=lambda x: _is_private_accelerator_ip(x), reverse=True)
    if rest:
        return rest[0], "router"
    return valid[0], "router"

# ---------- 打印当前网卡诊断信息 ----------
def print_network_report(gateway_ip):
    all_ips = get_all_ipv4()
    main_ip = get_main_ip()
    print("-" * 56)
    print("当前电脑检测到的 IPv4 地址：")
    for ip in all_ips:
        tags = []
        if ip.startswith("169.254."):
            tags.append("未连接/忽略")
        if ip == main_ip:
            tags.append("上网网卡")
        if ip == gateway_ip:
            tags.append("★选中为PS5网关")
        suffix = f"  （{', '.join(tags)}）" if tags else ""
        print(f"    {ip}{suffix}")
    print(f"默认上网网卡 IP：{main_ip or '未检测到（可能没联网）'}")
    print("-" * 56)
