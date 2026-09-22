# -*- coding: utf-8 -*-
"""
转推控制器：自动探测 MediaMTX 收到的 PS5 流，并调用 ffmpeg 推到目标
用法：
  python relay.py douyin     转推抖音（地址+推流码分开配置）
  python relay.py bilibili   转推B站
  python relay.py custom     转推到自定义RTMP后台（填完整URL）
"""
import sys
import json
import time
import subprocess
import urllib.request

from common import setup_utf8, load_config

MTX_API = "http://127.0.0.1:9997/v3/paths/list"
MTX_RTMP = "rtmp://127.0.0.1:1935"

PLATFORMS = {
    "douyin":   ("抖音", "抖音推流地址", "抖音推流码"),
    "bilibili": ("B站", "B站推流地址", "B站推流码"),
    # 自定义 RTMP 后台：直接使用完整 URL，不做地址/推流码拼接
    "custom":   ("自定义RTMP后台", "自定义推流地址", None),
}


def fetch_ps5_path(timeout_sec=120):
    """轮询 MediaMTX API，找到 PS5 推上来的 app/xxx 路径"""
    print("[..] 正在等待 PS5 推流到达本机（请确认 PS5 已开始 Twitch 直播）...")
    start = time.time()
    while time.time() - start < timeout_sec:
        try:
            with urllib.request.urlopen(MTX_API, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for item in data.get("items", []):
                name = item.get("name", "")
                ready = item.get("ready", False)
                if name.startswith("app/") and ready:
                    return name
        except Exception:
            pass
        print("    还没收到 PS5 流，2 秒后重试...（请确认①一键启动已运行、PS5已开播）")
        time.sleep(2)
    return None


def build_target(url, key):
    url = (url or "").strip().rstrip("/")
    key = (key or "").strip().lstrip("/")
    if not url:
        return ""
    return f"{url}/{key}" if key else url


def main():
    setup_utf8()
    if len(sys.argv) < 2 or sys.argv[1] not in PLATFORMS:
        print("用法：python relay.py douyin / bilibili / custom")
        input("按回车退出...")
        return

    plat_key = sys.argv[1]
    plat_name, url_key, code_key = PLATFORMS[plat_key]
    cfg = load_config()

    print("=" * 56)
    print(f"  转推到 {plat_name}")
    print("=" * 56)

    if code_key:
        # 抖音/B站：地址 + 推流码 拼接
        target = build_target(cfg.get(url_key, ""), cfg.get(code_key, ""))
    else:
        # 自定义后台：整串完整 URL 直接使用
        target = (cfg.get(url_key, "") or "").strip()
    if not target:
        if code_key:
            print(f"[错误] 还没在“推流配置.txt”里填写{plat_name}的推流地址/推流码！")
        else:
            print("[错误] 还没在“推流配置.txt”的“自定义推流地址=”后填写完整 RTMP URL！")
        print("请填好保存后再运行本脚本。")
        input("按回车退出...")
        return
    if not target.lower().startswith("rtmp"):
        print(f"[错误] 目标地址必须以 rtmp:// 或 rtmps:// 开头，当前为：{target}")
        input("按回车退出...")
        return

    reencode = cfg.get("重编码", "否").strip() in ("是", "yes", "y", "1", "true")

    ps5_path = fetch_ps5_path()
    if not ps5_path:
        print("[超时] 120 秒内没收到 PS5 推流。排查：")
        print("  1) “①一键启动”是否运行，DNS 窗口是否出现 [劫持] 日志")
        print("  2) MediaMTX 窗口是否出现 path app/xxx is ready")
        print("  3) PS5 是否已对 Twitch 开始直播、加速器是否正常")
        input("按回车退出...")
        return

    source = f"{MTX_RTMP}/{ps5_path}"
    print(f"[OK] 已捕获 PS5 本地流：{source}")
    print(f"[OK] 目标平台：{plat_name}")
    print(f"[OK] 编码方式：{'重新编码（兼容性好，占CPU）' if reencode else '直接转发（-c copy，几乎不占CPU）'}")
    print("-" * 56)

    if reencode:
        cmd = [
            "ffmpeg", "-i", source,
            "-c:v", "libx264", "-preset", "veryfast", "-b:v", "4000k",
            "-c:a", "aac", "-b:a", "128k",
            "-f", "flv", target,
        ]
    else:
        cmd = ["ffmpeg", "-i", source, "-c", "copy", "-f", "flv", target]

    print("即将执行：")
    # 打印时隐藏推流码，避免泄露
    safe_target = target.split("/")
    if len(safe_target) > 3:
        safe = "/".join(safe_target[:3]) + "/****（推流码已隐藏）"
    else:
        safe = target
    print("  " + " ".join(cmd[:-1]) + f' "{safe}"')
    print("-" * 56)
    print("ffmpeg 运行中。看到 frame=... fps=... 即推流成功。")
    print("到直播间确认画面；停止转推直接关闭本窗口或按 Ctrl+C。")
    print("=" * 56)

    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        pass
    except FileNotFoundError:
        print("[错误] 找不到 ffmpeg，请确认 ffmpeg 已安装并加入 PATH。")
    input("\n转推已结束，按回车关闭窗口...")


if __name__ == "__main__":
    main()
