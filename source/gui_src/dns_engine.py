# -*- coding: utf-8 -*-
"""
DNS 劫持引擎（由原 dns_proxy.py 重构）：
- 在后台线程内完成网卡检测、上游测速、绑定 0.0.0.0:53、持续服务；
- 通过 Qt 信号把结构化事件推给 GUI（不再打印黑窗口），驱动"5关"检测与错误归因。
"""
import time
import socket
import threading
import logging

from PySide6.QtCore import QObject, Signal

from dnslib import DNSRecord, RR, QTYPE, A
from dnslib.server import DNSServer, BaseResolver

import core

logging.getLogger("dnslib").setLevel(logging.CRITICAL)

INGEST_SUFFIXES = (".live-video.net", ".ingest.twitch.tv")
INGEST_EXACT = ("live.twitch.tv",)
AUTO_UPSTREAMS = ["8.8.8.1", "8.8.8.8", "223.5.5.5", "114.114.114.114"]
TEST_DOMAIN = "www.playstation.com"


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
        return False, ms, "响应里没有 A 记录"
    except socket.timeout:
        return False, 0, "超时/不可达"
    except Exception as e:
        return False, 0, str(e)[:40]


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
            socket.inet_aton(part)
        except OSError:
            continue
        if part not in out:
            out.append(part)
    return out or list(AUTO_UPSTREAMS)


class _SilentLogger:
    def __getattr__(self, name):
        return lambda *a, **k: None


class TwitchInterceptor(BaseResolver):
    def __init__(self, local_ip, upstreams, on_hijack, on_warn):
        self.local_ip = local_ip
        self.upstreams = upstreams
        self.fail_count = {}
        self.on_hijack = on_hijack
        self.on_warn = on_warn

    def resolve(self, request, handler):
        qname = str(request.q.qname).lower().rstrip(".")
        if is_ingest_domain(qname):
            reply = request.reply()
            if request.q.qtype == QTYPE.A:
                reply.add_answer(RR(request.q.qname, QTYPE.A,
                                    rdata=A(self.local_ip), ttl=30))
                self.on_hijack(qname, self.local_ip)
            else:
                self.on_hijack(qname, self.local_ip, empty=True)
            return reply

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
                if n <= 2 or n % 20 == 0:
                    self.on_warn("上游 %s 第 %d 次失败（%s）：%s"
                                 % (up, n, qname, last_err))
        self.on_warn("所有上游对 %s 解析失败：%s" % (qname, last_err))
        return request.reply()


class DnsEngine(QObject):
    # 日志：level∈ info/ok/warn/error，source 固定 "DNS"
    log = Signal(str, str, str)
    mode_detected = Signal(str, str)       # mode, local_ip
    upstream_tested = Signal(str, bool, int, str)  # ip, ok, ms, desc
    listening = Signal(str)                # local_ip
    hijacked = Signal(str, str)            # domain, ip
    fatal = Signal(str, str)               # reason_code, 人类可读说明
    started = Signal()
    stopped = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._server = None
        self._stop_event = threading.Event()
        self.local_ip = None
        self.mode = ""
        self.hijack_count = 0

    # ---------- 生命周期 ----------
    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, manual_gw="", upstream_cfg="自动"):
        if self.is_running():
            return
        self._stop_event.clear()
        self.hijack_count = 0
        self._thread = threading.Thread(
            target=self._run, args=(manual_gw, upstream_cfg), daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        try:
            if self._server is not None:
                self._server.stop()
        except Exception:
            pass
        if self._thread is not None:
            self._thread.join(timeout=3)
        self._thread = None
        self.stopped.emit()

    # ---------- 事件回调（dnslib 线程触发） ----------
    def _on_hijack(self, domain, ip, empty=False):
        self.hijack_count += 1
        if not empty:
            self.hijacked.emit(domain, ip)
            self.log.emit("ok", "DNS", "劫持成功：%s -> %s" % (domain, ip))
        else:
            self.log.emit("info", "DNS", "劫持 %s（非 A 查询，强制走 IPv4）" % domain)

    def _on_warn(self, msg):
        self.log.emit("warn", "DNS", msg)

    # ---------- 主流程 ----------
    def _run(self, manual_gw, upstream_cfg):
        try:
            self.log.emit("info", "DNS", "正在检测本机网卡与局域网 IP…")
            local_ip, mode = core.detect_gateway_ip(manual_gw)
            self.local_ip, self.mode = local_ip, mode
            if not local_ip:
                self._emit_fatal("no_ip",
                    "本机没有可用的局域网 IPv4 地址。请确认电脑已用网线/WiFi 连网"
                    "（并已开启加速器），再重试；也可在设置里手动填写网关IP。")
                return
            self.mode_detected.emit(mode, local_ip)
            mode_txt = {"direct": "直连模式（PS5 网线直连电脑，电脑当网关）",
                        "router": "局域网模式（PS5 与电脑连同一个路由器）",
                        "manual": "手动指定电脑 IP"}.get(mode, mode)
            self.log.emit("ok", "DNS", "识别为：%s；PS5 首选 DNS = %s"
                         % (mode_txt, local_ip))

            candidates = parse_upstreams(upstream_cfg)
            self.log.emit("info", "DNS", "正在测速上游 DNS（决定 PS5 改完 DNS 后是否断网）…")
            usable, unusable = [], []
            for up in candidates:
                if self._stop_event.is_set():
                    return
                ok, ms, desc = test_upstream(up)
                self.upstream_tested.emit(up, ok, ms, desc)
                if ok:
                    usable.append((up, ms))
                    self.log.emit("ok", "DNS", "上游 %s 可用，%dms（%s）" % (up, ms, desc))
                else:
                    unusable.append(up)
                    self.log.emit("warn", "DNS", "上游 %s 不通：%s（已跳过）" % (up, desc))

            if not usable:
                self._emit_fatal("no_upstream",
                    "所有上游 DNS 都不可用——此时让 PS5 改 DNS 会直接断网。\n"
                    "请检查：① 电脑现在能否正常上网；② 加速器是否已连接（换个节点）；"
                    "③ 在【设置】把上游 DNS 改成加速器给的 DNS（如 AK 默认 8.8.8.1）后重开。")
                return

            usable.sort(key=lambda x: x[1])
            upstreams = [u for u, _ in usable] + unusable
            self.log.emit("ok", "DNS", "已选定最快上游：%s（其余作为备用）" % upstreams[0])

            resolver = TwitchInterceptor(local_ip, upstreams,
                                         self._on_hijack, self._on_warn)
            try:
                server = DNSServer(resolver=resolver, port=53, address="0.0.0.0",
                                   logger=_SilentLogger())
                server.start_thread()
                self._server = server
            except PermissionError:
                self._emit_fatal("bind_permission",
                    "没有权限绑定 53 端口。请以管理员身份运行本程序（EXE 会自动申请，"
                    "若被拒绝请右键“以管理员身份运行”）。")
                return
            except OSError as e:
                detail = str(e)
                owners = core.port_listeners(53, ("tcp", "udp"))
                who = "；".join("%s(%s) [%s/%s]" % (n, pid, proto, addr)
                                for pid, n, addr, proto in owners)
                extra = ("检测到 53 端口被占用：%s。\n" % who if who else "")
                self._emit_fatal("bind_inuse",
                    "53 端口无法绑定。%s多半是加速器的 DNS 代理（或系统 DNS 服务）占用："
                    "请先一键停止，再以管理员身份重启；若仍失败，需要在加速器设置里关闭"
                    "它的“DNS 代理/DNS 劫持”。原始错误：%s" % (extra, detail))
                return

            # 短暂等待，确认服务线程存活
            time.sleep(0.6)
            if self._stop_event.is_set():
                return
            self.listening.emit(local_ip)
            self.log.emit("ok", "DNS", "DNS 服务已就绪，监听 0.0.0.0:53，等待 PS5 查询…")
            self.started.emit()

            while not self._stop_event.is_set():
                time.sleep(0.5)
        finally:
            try:
                if self._server is not None:
                    self._server.stop()
            except Exception:
                pass
            self.log.emit("info", "DNS", "DNS 服务已停止。")
            self._server = None
            self.stopped.emit()

    def _emit_fatal(self, code, detail):
        self.log.emit("error", "DNS", "致命错误：" + detail.replace("\n", " "))
        self.fatal.emit(code, detail)
