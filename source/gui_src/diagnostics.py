# -*- coding: utf-8 -*-
"""
诊断与“5 关”评估：把所有异常明确归因到具体设备，并给出可操作的修复步骤。
设备标签：本机电脑 / 网络·路由器 / PS5主机 / 加速器 / 推流后台 / 配置 / DNS / MediaMTX
"""
import time

import core
from dns_engine import test_upstream, parse_upstreams

# 设备 → 主题色键（QSS 中定义）
DEVICES = {
    "pc":       "本机电脑",
    "network":  "网络·路由器",
    "ps5":      "PS5主机",
    "accel":    "加速器",
    "backend":  "推流后台/平台",
    "config":   "配置",
    "dns":      "DNS服务",
    "mtx":      "MediaMTX",
}

# 检查级别
OK, WARN, ERROR = "ok", "warn", "error"


class CheckResult:
    def __init__(self, key, title, level, device, detail, suggestion=""):
        self.key = key
        self.title = title
        self.level = level
        self.device = device
        self.detail = detail
        self.suggestion = suggestion

    def __repr__(self):
        return "<%s %s %s>" % (self.key, self.level, self.device)


# ---------------------------------------------------------------------------
# 前置体检（一键启动前跑，网络测速在子线程内执行，避免卡 UI）
# ---------------------------------------------------------------------------
def run_preflight(cfg, platform="custom", quick=False):
    results = []

    # 1) 管理员权限
    if core.is_admin():
        results.append(CheckResult(
            "admin", "管理员权限", OK, "pc",
            "已获得管理员权限（可绑定 53 端口、写入防火墙）。"))
    else:
        results.append(CheckResult(
            "admin", "管理员权限", ERROR, "pc",
            "当前没有以管理员身份运行。",
            "请关闭本程序后，右键“以管理员身份运行”，或直接双击（EXE 会自动弹出 UAC，点“是”）。"
            "否则无法开启 DNS 劫持（53 端口），也无法添加防火墙规则。"))

    # 2) mediamtx 文件
    if core.find_mediamtx():
        results.append(CheckResult(
            "mediamtx", "MediaMTX 收流程序", OK, "mtx",
            "已找到 mediamtx.exe。"))
    else:
        results.append(CheckResult(
            "mediamtx", "MediaMTX 收流程序", ERROR, "mtx",
            "在工具目录的 mediamtx 文件夹内找不到 mediamtx.exe。",
            "请把完整的 mediamtx 文件夹放回程序同级目录；不要只移动 EXE。"))

    # 3) ffmpeg（仅转推需要）
    if core.find_ffmpeg():
        results.append(CheckResult(
            "ffmpeg", "ffmpeg 转推程序", OK, "pc",
            "已找到 ffmpeg：%s" % core.find_ffmpeg()))
    else:
        results.append(CheckResult(
            "ffmpeg", "ffmpeg 转推程序", WARN, "pc",
            "未找到 ffmpeg（不影响收流/监看，但“转推”不可用）。",
            "安装 ffmpeg 并加入系统 PATH，或把 ffmpeg.exe 放到工具目录的 ffmpeg 文件夹内后重开程序。"))

    # 4) 本机联网与 IP
    all_ips = core.get_all_ipv4()
    main_ip = core.get_main_ip()
    gw_ip, mode = core.detect_gateway_ip(cfg.get("网关IP", ""))
    if main_ip and gw_ip:
        mode_txt = {"direct": "直连", "router": "局域网", "manual": "手动"}.get(mode, mode)
        results.append(CheckResult(
            "ip", "本机网络", OK, "pc",
            "检测到上网网卡 IP：%s；将让 PS5 把首选 DNS 填为 %s（%s模式）。"
            % (main_ip, gw_ip, mode_txt)))
    else:
        results.append(CheckResult(
            "ip", "本机网络", ERROR, "pc",
            "未检测到可用的局域网 IP（电脑可能没联网）。",
            "请确认电脑已用网线/WiFi 连网，并已开启加速器；若为特殊网络，可在设置里手动填写网关IP。"))

    # 5) 53 端口占用
    owners53 = core.port_listeners(53, ("tcp", "udp"))
    # 排除我们自己的占用（已运行时）
    owners53 = [o for o in owners53 if o[1] not in ("mediamtx.exe",)]
    if owners53:
        who = "；".join("%s（%s，%s/%s）" % (n, pid, proto, addr)
                        for pid, n, addr, proto in owners53)
        results.append(CheckResult(
            "port53", "53 端口（DNS）", WARN, "pc",
            "53 端口当前被占用：%s" % who,
            "若占用方是加速器（AK 等）的 DNS 代理，请先在加速器里关闭“DNS 代理/DNS 劫持”，"
            "或先一键停止再以管理员重启；否则 DNS 服务无法绑定（现象：PS5 改 DNS 后断网）。"))
    else:
        results.append(CheckResult(
            "port53", "53 端口（DNS）", OK, "pc", "53 端口空闲，DNS 服务可正常绑定。"))

    # 6) 1935 端口占用
    owners1935 = core.port_listeners(1935, ("tcp",))
    if owners1935:
        who = "；".join("%s（%s，%s）" % (n, pid, addr) for pid, n, addr, proto in owners1935)
        if all("mediamtx" in n for _, n, _, _ in owners1935):
            results.append(CheckResult(
                "port1935", "1935 端口（RTMP）", OK, "mtx",
                "1935 已由 MediaMTX 占用（说明收流服务已在运行）。"))
        else:
            results.append(CheckResult(
                "port1935", "1935 端口（RTMP）", WARN, "pc",
                "1935 端口被其他程序占用：%s" % who,
                "请关闭占用该端口的程序（其他直播/推流软件），否则 MediaMTX 收不到流。"))
    else:
        results.append(CheckResult(
            "port1935", "1935 端口（RTMP）", OK, "mtx", "1935 端口空闲，MediaMTX 可正常收流。"))

    # 7) 上游 DNS 测速（最耗时）
    if not quick:
        candidates = parse_upstreams(cfg.get("上游DNS", "自动"))
        usable = []
        detail_lines = []
        for up in candidates:
            ok, ms, desc = test_upstream(up, timeout=2.0)
            if ok:
                usable.append((up, ms))
                detail_lines.append("%s %dms" % (up, ms))
            else:
                detail_lines.append("%s 不通" % up)
        if usable:
            usable.sort(key=lambda x: x[1])
            results.append(CheckResult(
                "upstream", "上游 DNS（决定 PS5 改 DNS 后能否联网）", OK, "accel",
                "可用上游：%s；最快：%s（%dms）。"
                % ("、".join(detail_lines), usable[0][0], usable[0][1])))
        else:
            results.append(CheckResult(
                "upstream", "上游 DNS（决定 PS5 改 DNS 后能否联网）", ERROR, "accel",
                "所有上游 DNS 都不可达：%s。" % "、".join(detail_lines),
                "此时让 PS5 改 DNS 必断网。请确认：① 电脑现在能上网；② 加速器已连接（可换节点）；"
                "③ 到设置把上游 DNS 改成加速器给的 DNS（如 AK 默认 8.8.8.1）。"))

    # 8) 推流目标配置（静态校验）
    from workers import PLATFORMS
    name, url_key, code_key = PLATFORMS[platform]
    if platform == "custom":
        val = (cfg.get("自定义推流地址", "") or "").strip()
        if not val:
            results.append(CheckResult(
                "target", "转推目标（%s）" % name, WARN, "config",
                "还没填写自定义推流地址（不影响收流/监看，但不能转推）。",
                "到【设置】把 RTMP 后台给的完整地址粘贴到“自定义推流地址”，必须 rtmp:// 开头。"))
        elif not val.lower().startswith("rtmp"):
            results.append(CheckResult(
                "target", "转推目标（%s）" % name, ERROR, "config",
                "自定义推流地址不是 rtmp:// 开头：%s" % val,
                "请粘贴 RTMP 后台给的完整 URL（rtmp:// 或 rtmps:// 开头）。"))
        else:
            results.append(CheckResult(
                "target", "转推目标（%s）" % name, OK, "backend", "自定义推流地址已填写。"))
    else:
        u = (cfg.get(url_key, "") or "").strip()
        k = (cfg.get(code_key, "") or "").strip()
        if u and k:
            if u.lower().startswith("rtmp"):
                results.append(CheckResult(
                    "target", "转推目标（%s）" % name, OK, "backend",
                    "%s推流地址与推流码已填写。" % name))
            else:
                results.append(CheckResult(
                    "target", "转推目标（%s）" % name, ERROR, "config",
                    "推流地址不是 rtmp:// 开头。", "请核对后重新粘贴。"))
        else:
            results.append(CheckResult(
                "target", "转推目标（%s）" % name, WARN, "config",
                "%s推流地址或推流码未填全。" % name,
                "到【设置】补全推流地址与推流码；注意推流码每次开播可能变化。"))

    return results


# ---------------------------------------------------------------------------
# 5 关定义
# ---------------------------------------------------------------------------
PENDING, ACTIVE, OKS, FAIL = "pending", "active", "ok", "fail"

GATES = [
    {"id": "g1", "title": "服务启动", "device": "pc",
     "ok": "防火墙就绪、MediaMTX 监听 1935、DNS 监听 53",
     "wait": "正在启动本机收流与 DNS 服务…"},
    {"id": "g2", "title": "上游网络", "device": "accel",
     "ok": "上游 DNS 可达，PS5 改 DNS 后不会断网",
     "wait": "正在测速上游 DNS…"},
    {"id": "g3", "title": "劫持成功", "device": "ps5",
     "ok": "PS5 已开始 Twitch 直播，推流域名被引到电脑",
     "wait": "等待 PS5 开始 Twitch 直播…"},
    {"id": "g4", "title": "画面到达", "device": "network",
     "ok": "MediaMTX 已收到 PS5 画面（path app/xxx is ready）",
     "wait": "等待画面到达电脑…"},
    {"id": "g5", "title": "转推成功", "device": "backend",
     "ok": "ffmpeg 持续推送（frame 持续增长），后台可见画面",
     "wait": "等待转推…"},
]

# 每关卡住/失败时的排查指引（设备, 现象, 解决）
GATE_HELP = {
    "g1": {
        "fail_device": "pc",
        "tips": [
            ("DNS服务", "出现“53 端口无法绑定”", "多为加速器的 DNS 代理占用 53：一键停止后以管理员重启；仍失败就在加速器里关闭“DNS 代理/DNS 劫持”。"),
            ("本机电脑", "防火墙三条未全部 OK", "UAC 弹窗点“是”，确认以管理员身份运行；可在诊断页重新一键加规则。"),
            ("MediaMTX", "MediaMTX 没监听 1935", "1935 被其他推流软件占用，关闭后重试；确认 mediamtx.exe 存在且未被杀毒拦截。"),
        ],
    },
    "g2": {
        "fail_device": "accel",
        "tips": [
            ("加速器", "所有上游 DNS 都不通", "确认电脑此刻能上网、加速器已连接（换个节点）；到设置把上游 DNS 改成加速器给的 8.8.8.1。"),
            ("本机电脑", "电脑自身断网", "先恢复电脑网络，再启动服务。"),
        ],
    },
    "g3": {
        "fail_device": "ps5",
        "tips": [
            ("PS5主机", "首选 DNS 没填对/没保存", "PS5 网络设置里，首选 DNS 必须填界面顶部显示的电脑 IP，备选 DNS 留空；IP/掩码/网关照抄加速器。"),
            ("PS5主机", "没有真正开始 Twitch 直播", "进游戏 → 创建键 → 直播 → Twitch → 开始直播（需先在 twitch.tv/activate 完成绑定）。"),
            ("网络·路由器", "PS5 与电脑不在同一路由器", "确认 PS5 和电脑连的是同一个家用路由器（局域网模式），不是直连电脑、也不是不同网络。"),
            ("加速器", "PS5 测试互联网连接失败", "先让 PS5 能上网：前 3 项照抄加速器，唯独首选 DNS 换成电脑 IP，备选清空。"),
        ],
    },
    "g4": {
        "fail_device": "network",
        "tips": [
            ("PS5主机", "已劫持但没有 is ready", "PS5 端直播可能未真正开始推送，重新开始一次 Twitch 直播。"),
            ("MediaMTX", "MediaMTX 未运行/报错", "回到第 1 关确认 MediaMTX 正常监听 1935；重启一键启动。"),
            ("网络·路由器", "PS5 与电脑链路不通", "确认两者同一局域网，必要时在路由器上关闭 AP 隔离/客户端隔离。"),
        ],
    },
    "g5": {
        "fail_device": "backend",
        "tips": [
            ("推流后台/平台", "ffmpeg 报连接重置/404", "推流地址或推流码错误/过期，重新从后台复制；抖音/B站推流码每次开播会变。"),
            ("本机电脑", "ffmpeg 在跑但后台黑屏", "到设置把【重编码】改为“是”（后台不支持直接转发时必须重编码），再重新转推。"),
            ("PS5主机", "一直“还没收到 PS5 流”", "说明第 3/4 关没过，画面根本没到电脑，先解决劫持和收流。"),
            ("本机电脑", "找不到 ffmpeg", "安装 ffmpeg 并加入 PATH，或把 ffmpeg.exe 放到工具目录的 ffmpeg 文件夹。"),
        ],
    },
}


class AppState:
    """集中保存运行态，供 5 关评估。"""
    def __init__(self):
        self.started = False
        # G1
        self.firewall_ok = False
        self.firewall_done = False
        self.mtx_1935 = False
        self.dns_listening = False
        self.dns_fatal = None          # (code, detail)
        # G2
        self.upstream_usable = 0
        self.upstream_total = 0
        # G3
        self.hijack_count = 0
        self.last_hijack = ""
        self.last_hijack_ts = 0
        # G4
        self.stream_ready = False
        self.stream_path = ""
        # G5
        self.relay_stage = "idle"      # idle/waiting/pushing/done/error
        self.relay_frame = -1
        self.relay_frame_moving = False
        self.relay_error = None
        # 时间戳
        self.started_ts = 0
        self.dns_listening_ts = 0
        self.stream_ready_ts = 0
        self.pushing_ts = 0

    def reset(self):
        self.__init__()


def evaluate(state):
    """返回每关 {status, detail, device}，以及整体结论。"""
    out = []
    S = state

    # ---------- G1 ----------
    if not S.started:
        g1 = (PENDING, "未启动", "pc")
    elif S.dns_fatal and S.dns_fatal[0] in ("bind_permission", "bind_inuse", "no_ip"):
        g1 = (FAIL, "服务未能就绪：%s" % S.dns_fatal[1].split("。")[0], "pc")
    elif S.mtx_1935 and S.dns_listening:
        g1 = (OKS, "MediaMTX 与 DNS 均已就绪", "pc")
    else:
        g1 = (ACTIVE, "正在启动本机服务…", "pc")
    out.append(g1)

    # ---------- G2 ----------
    if not S.started:
        g2 = (PENDING, "未启动", "accel")
    elif S.dns_fatal and S.dns_fatal[0] == "no_upstream":
        g2 = (FAIL, "所有上游 DNS 都不通，PS5 改 DNS 会断网", "accel")
    elif S.upstream_usable > 0:
        g2 = (OKS, "%d/%d 个上游可用" % (S.upstream_usable, S.upstream_total or S.upstream_usable), "accel")
    else:
        g2 = (ACTIVE, "正在测速上游 DNS…", "accel")
    out.append(g2)

    # ---------- G3 ----------
    if not S.dns_listening:
        g3 = (PENDING, "等待 DNS 服务就绪", "ps5")
    elif S.hijack_count > 0:
        g3 = (OKS, "已劫持 %d 次：%s" % (S.hijack_count, S.last_hijack), "ps5")
    else:
        g3 = (ACTIVE, "请在 PS5 上开始 Twitch 直播", "ps5")
    out.append(g3)

    # ---------- G4 ----------
    if S.stream_ready:
        g4 = (OKS, "已收到画面：%s" % S.stream_path, "network")
    elif S.hijack_count > 0:
        g4 = (ACTIVE, "已劫持，等待 MediaMTX 收到画面…", "network")
    else:
        g4 = (PENDING, "等待劫持成功", "network")
    out.append(g4)

    # ---------- G5 ----------
    if S.relay_stage == "pushing":
        if S.relay_frame_moving:
            g5 = (OKS, "正在转推，frame=%d" % S.relay_frame, "backend")
        else:
            g5 = (ACTIVE, "ffmpeg 已启动，等待画面帧…", "backend")
    elif S.relay_stage == "waiting":
        g5 = (ACTIVE, "正在等待 PS5 流，准备转推…", "backend")
    elif S.relay_stage == "error":
        g5 = (FAIL, (S.relay_error or "转推异常")[:60], "backend")
    elif S.relay_stage == "done":
        g5 = (OKS, "转推已结束", "backend")
    else:
        g5 = (PENDING, "未开始转推", "backend")
    out.append(g5)

    # 整体结论：找第一个“应该过但没过”的关
    diagnosis = None
    if S.started:
        for idx, (status, detail, device) in enumerate(out):
            gate = GATES[idx]
            if status == FAIL:
                diagnosis = (gate["id"], "error", device, gate["title"], detail)
                break
        # 长时间卡在某关给出提示（不阻断）
        if diagnosis is None:
            now = time.time()
            if S.dns_listening and S.hijack_count == 0 and now - S.dns_listening_ts > 30:
                diagnosis = ("g3", "wait", "ps5", "劫持成功",
                             "DNS 已就绪 30 秒还没出现劫持。请在 PS5 上开始 Twitch 直播，"
                             "并确认首选 DNS 填的是界面顶部的电脑 IP、备选 DNS 留空。")
            elif S.hijack_count > 0 and not S.stream_ready and S.last_hijack_ts and now - S.last_hijack_ts > 20:
                diagnosis = ("g4", "wait", "network", "画面到达",
                             "已劫持但 20 秒内没收到画面，请在 PS5 重新开始一次直播，确认 PS5 与电脑同一局域网。")
            elif S.relay_stage == "pushing" and not S.relay_frame_moving and S.pushing_ts and now - S.pushing_ts > 20:
                diagnosis = ("g5", "wait", "backend", "转推成功",
                             "ffmpeg 已启动但一直没有画面帧：先确认第 4 关已收到画面；若持续如此，把【重编码】改为“是”。")

    gates = []
    for i, gate in enumerate(GATES):
        status, detail, device = out[i]
        gates.append({"gate": gate, "status": status, "detail": detail, "device": device})
    return gates, diagnosis
