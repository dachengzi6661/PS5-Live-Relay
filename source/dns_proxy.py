# -*- coding: utf-8 -*-
"""
DNS Hijack Server (console output is ENGLISH on purpose to avoid any CJK
codepage garbling in this particular window).
- Twitch ingest domains are hijacked to this PC's LAN IP.
- Every other domain is forwarded to working upstream DNS (PS5 stays online),
  with automatic upstream speed test and failover.
"""
import time
import socket
import logging
from dnslib import DNSRecord, RR, QTYPE, A
from dnslib.server import DNSServer, BaseResolver

from common import (
    setup_utf8, load_config, detect_gateway_ip,
    get_all_ipv4, get_main_ip,
)

# Keep this window quiet (dnslib logs every query otherwise)
logging.getLogger("dnslib").setLevel(logging.CRITICAL)

# Twitch ingest domain suffixes. .live-video.net covers all modern ingest
# hosts (*.contribute.live-video.net, gss*.live-video.net, ...)
INGEST_SUFFIXES = (
    ".live-video.net",
    ".ingest.twitch.tv",
)
INGEST_EXACT = ("live.twitch.tv",)

# Auto upstream candidates: accelerator DNS first, public DNS as fallback
AUTO_UPSTREAMS = ["8.8.8.1", "8.8.8.8", "223.5.5.5", "114.114.114.114"]
TEST_DOMAIN = "www.playstation.com"


class _SilentLogger:
    """Swallow dnslib's per-query Request/Reply spam."""
    def __getattr__(self, name):
        return lambda *a, **k: None


def is_ingest_domain(domain):
    d = domain.lower().rstrip(".")
    if d in INGEST_EXACT:
        return True
    return any(d.endswith(suf) for suf in INGEST_SUFFIXES)


def test_upstream(ip, timeout=2.0):
    try:
        q = DNSRecord.question(TEST_DOMAIN)
        t0 = time.time()
        ans = DNSRecord.parse(q.send(ip, 53, timeout=timeout, tcp=False))
        ms = int((time.time() - t0) * 1000)
        addrs = [str(rr.rdata) for rr in ans.rr if rr.rtype == QTYPE.A]
        if addrs:
            return True, ms, "resolved " + addrs[0]
        return False, ms, "no A record in reply"
    except socket.timeout:
        return False, 0, "timeout / unreachable"
    except Exception as e:
        return False, 0, str(e)[:40]


class TwitchInterceptor(BaseResolver):
    def __init__(self, local_ip, upstreams):
        self.local_ip = local_ip
        self.upstreams = upstreams
        self.fail_count = {}

    def resolve(self, request, handler):
        qname = str(request.q.qname).lower().rstrip(".")

        if is_ingest_domain(qname):
            reply = request.reply()
            if request.q.qtype == QTYPE.A:
                reply.add_answer(RR(
                    request.q.qname, QTYPE.A,
                    rdata=A(self.local_ip), ttl=30
                ))
                print("[HIJACK] %s (A) -> %s" % (qname, self.local_ip))
            else:
                # Empty AAAA/other reply to force IPv4 to this PC
                print("[HIJACK] %s (qtype %s) empty, force IPv4"
                      % (qname, request.q.qtype))
            return reply

        # Forward everything else, fail over across upstreams
        last_err = ""
        for up in self.upstreams:
            try:
                resp = DNSRecord.parse(request.send(up, 53, timeout=3))
                resp.header.id = request.header.id
                return resp
            except Exception as e:
                last_err = str(e)[:40]
                self.fail_count[up] = self.fail_count.get(up, 0) + 1
                n = self.fail_count[up]
                if n <= 3 or n % 20 == 0:
                    print("[upstream %s failed x%d, next] %s: %s"
                          % (up, n, qname, last_err))
        print("[WARN] all upstreams failed for %s: %s" % (qname, last_err))
        return request.reply()


def parse_upstreams(cfg_value):
    v = (cfg_value or "").strip()
    if not v or v.lower() in ("auto", "自动"):
        return list(AUTO_UPSTREAMS)
    out = []
    for part in v.replace("，", ",").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            socket.inet_aton(part)  # must be a valid IPv4 literal
        except OSError:
            print("[WARN] ignore invalid upstream DNS entry: %s" % part)
            continue
        if part not in out:
            out.append(part)
    return out or list(AUTO_UPSTREAMS)


def print_lan_report(chosen):
    all_ips = get_all_ipv4()
    main_ip = get_main_ip()
    print("-" * 56)
    print("Detected IPv4 addresses on this PC:")
    for ip in all_ips:
        tags = []
        if ip.startswith("169.254."):
            tags.append("disconnected/ignored")
        if ip == main_ip:
            tags.append("internet adapter")
        if ip == chosen:
            tags.append("* USE THIS AS PS5 PRIMARY DNS")
        suffix = ("  (%s)" % ", ".join(tags)) if tags else ""
        print("    %s%s" % (ip, suffix))
    print("Default internet adapter IP: %s" % (main_ip or "none (offline?)"))
    print("-" * 56)


def main():
    setup_utf8()
    cfg = load_config()

    candidates = parse_upstreams(cfg.get("上游DNS", ""))
    manual_gw = cfg.get("网关IP", "").strip()

    print("=" * 56)
    print("           PS5 Live - DNS Hijack Server")
    print("=" * 56)

    local_ip, mode = detect_gateway_ip(manual_gw)
    print_lan_report(local_ip)

    if not local_ip:
        print("[ERROR] No usable LAN IP found on this PC.")
        print("Make sure the PC is online (WiFi/Ethernet connected), then retry.")
        print("You can also manually set gateway IP in the config file.")
        print("-" * 56)
        input("Press Enter to exit...")
        return

    if mode == "direct":
        print("[MODE] DIRECT mode: PS5 is cabled straight to this PC (PC = gateway).")
    elif mode == "router":
        print("[MODE] LAN-ROUTER mode: PS5 and this PC are on the SAME router.")
    else:
        print("[MODE] Using manually configured PC IP: %s" % local_ip)

    # ---- Test upstreams ----
    print("[..] Testing upstream DNS (decides whether PS5 stays online)...")
    usable, unusable = [], []
    for up in candidates:
        ok, ms, desc = test_upstream(up)
        if ok:
            usable.append((up, ms))
            print("     [OK ] %-16s %5dms  %s" % (up, ms, desc))
        else:
            unusable.append(up)
            print("     [BAD] %-16s %s" % (up, desc))

    if not usable:
        print("-" * 56)
        print("[FATAL] No upstream DNS works! PS5 would lose internet in this state.")
        print("Checks:")
        print("  1) Can THIS PC browse the internet right now?")
        print("  2) Is the accelerator actually connected? Try another node.")
        print("  3) Set upstream DNS in the config to the accelerator DNS (e.g. 8.8.8.1)")
        print("-" * 56)
        input("Press Enter to exit...")
        return

    usable.sort(key=lambda x: x[1])
    upstreams = [u for u, _ in usable] + unusable
    print("[OK] Primary upstream: %s (rest are backup)" % upstreams[0])
    if unusable:
        print("     (%s unusable now, skipped)" % ", ".join(unusable))

    print("-" * 56)
    print("[OK] Twitch ingest domains hijacked to this PC : %s" % local_ip)
    print("[OK] Other domains forwarded upstream (PS5 keeps working online)")
    print("-" * 56)
    if mode == "router":
        print("[!!] PS5 SETTINGS (LAN-ROUTER mode):")
        print("     Keep IP / Subnet Mask / Gateway EXACTLY as the accelerator gave.")
        print("     >>> Set PS5 PRIMARY DNS = %s" % local_ip)
        print("     >>> Set PS5 SECONDARY DNS = (blank / 0.0.0.0)")
        print("     PS5 connects to the ROUTER by cable or WiFi -- NOT to this PC.")
    else:
        print("[!!] PS5 SETTINGS (DIRECT mode):")
        print("     >>> PRIMARY DNS = %s , SECONDARY DNS = blank" % local_ip)
    print("=" * 56)

    # ---- Bind port 53 with clear error reporting ----
    resolver = TwitchInterceptor(local_ip, upstreams)
    try:
        server = DNSServer(resolver=resolver, port=53, address="0.0.0.0",
                           logger=_SilentLogger())
        server.start_thread()
    except PermissionError:
        print("[FATAL] No permission to bind port 53.")
        print("Please launch through the step-1 START script (it requests admin).")
        input("Press Enter to exit...")
        return
    except OSError as e:
        print("[FATAL] Cannot bind port 53: %s" % e)
        print("Another program (maybe the accelerator) is using port 53.")
        print("Run step-3 STOP, then re-open step-1 START as administrator.")
        input("Press Enter to exit...")
        return

    time.sleep(0.5)
    print("[OK] Listening on 0.0.0.0:53, waiting for PS5 DNS queries...")
    print("     When PS5 starts the Twitch broadcast, [HIJACK] lines appear here.")
    print("-" * 56)
    print("Running. Do NOT close this window. Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping DNS server...")
        server.stop()


if __name__ == "__main__":
    main()
