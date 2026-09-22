# -*- coding: utf-8 -*-
"""
Local monitor:
  - find the PS5 stream from MediaMTX automatically,
  - open its built-in read page in the browser,
  - build and copy the RTMP / HLS pull URLs (for OBS / Douyin Live Companion).
Console output is ENGLISH on purpose (avoids any CJK codepage garbling).

Usage:
  python monitor.py        WebRTC page, low latency (~1s), recommended
  python monitor.py hls    HLS page, compatible (~3-8s)
"""
import sys
import json
import time
import subprocess
import webbrowser
import urllib.request

from common import setup_utf8

MTX_API = "http://127.0.0.1:9997/v3/paths/list"
URLS_FILE = "stream_urls.txt"


def set_clipboard(text):
    """Copy pure-ASCII text to the Windows clipboard via clip.exe."""
    try:
        p = subprocess.run(["clip"], input=text.encode("ascii", "replace"),
                           timeout=3, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        return p.returncode == 0
    except Exception:
        return False


def list_ready_paths(timeout_sec=15):
    """Poll the API and return all ready path names."""
    start = time.time()
    while time.time() - start < timeout_sec:
        try:
            with urllib.request.urlopen(MTX_API, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            ready = [it["name"] for it in data.get("items", []) if it.get("ready")]
            if ready:
                return ready, data.get("items", [])
        except Exception:
            pass
        print("    Not connected yet, retry in 2s... (run step-1 START and go live on PS5)")
        time.sleep(2)
    return [], []


def pick_ps5_path(names):
    for n in names:
        if n.startswith("app/"):
            return n
    return names[0] if names else ""


def main():
    setup_utf8()
    mode = "hls" if (len(sys.argv) > 1 and sys.argv[1].lower() in ("hls", "h")) else "webrtc"
    mode_label = "HLS compatible page (~3-8s)" if mode == "hls" else "WebRTC low-latency page (~1s)"

    print("=" * 60)
    print("  PS5 Local Monitor  -  " + mode_label)
    print("=" * 60)
    print("[..] Reading online streams from MediaMTX ...")

    names, items = list_ready_paths()
    if not names:
        print("[TIMEOUT] No online stream found. Check in order:")
        print("  1) step-1 START was run and the MediaMTX window is open")
        print("  2) PS5 has started the Twitch broadcast")
        print("  3) the DNS window shows [HIJACK] lines")
        input("\nPress Enter to exit...")
        return

    print("[OK] %d online stream(s):" % len(names))
    for it in items:
        if it.get("ready"):
            tag = "  <- PS5 source" if it["name"].startswith("app/") else ""
            print("     - " + it["name"] + tag)

    t = pick_ps5_path(names)
    webrtc_page = "http://127.0.0.1:8889/%s/" % t
    hls_page = "http://127.0.0.1:8888/%s/" % t
    rtmp_url = "rtmp://127.0.0.1:1935/%s" % t
    hls_url = "http://127.0.0.1:8888/%s/index.m3u8" % t
    open_page = hls_page if mode == "hls" else webrtc_page

    print("-" * 60)
    print("WATCH IN BROWSER (web pages):")
    print("  WebRTC (low latency): " + webrtc_page)
    print("  HLS   (compatible) : " + hls_page)
    print("-" * 60)
    print("PULL URLS -> paste into OBS / Douyin Live Companion")
    print("(Add Source > Network Stream/Media; do NOT use the web pages):")
    print("  RTMP : " + rtmp_url)
    print("  HLS  : " + hls_url)
    print("-" * 60)

    if set_clipboard(rtmp_url):
        print("[OK] RTMP pull URL copied to clipboard. Just Ctrl+V in the app.")
    else:
        print("[WARN] Auto-copy failed; copy the RTMP line manually.")

    try:
        with open(URLS_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join([
                "PS5 stream pull URLs",
                "",
                "RTMP : " + rtmp_url,
                "HLS  : " + hls_url,
                "",
                "WebRTC page: " + webrtc_page,
                "HLS page   : " + hls_page,
                "",
            ]))
        print("[OK] All URLs also saved to file: " + URLS_FILE + " (in this folder)")
    except Exception:
        pass

    print("-" * 60)
    print("[..] Opening watch page: " + open_page)
    webbrowser.open(open_page)
    print("If this page is black, close it and run the HLS-compatible monitor.")
    input("\nPress Enter to close this window...")


if __name__ == "__main__":
    main()
