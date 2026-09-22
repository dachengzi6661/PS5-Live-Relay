# -*- coding: utf-8 -*-
"""
进程与转推管理：
- Proc：QProcess 通用封装，实时把输出按行推给 GUI（替代黑窗口）；
- MediaMTX：启动 mediamtx.exe，解析 1935 监听、path ready、端口占用；
- RelayManager：自动找 PS5 流、调用 ffmpeg 转推、解析 frame/fps 进度与报错；
- fetch_paths：查询 MediaMTX API 在线流。
"""
import os
import re
import json
import time
import urllib.request

from PySide6.QtCore import QObject, Signal, QProcess, QTimer, QUrl
from PySide6.QtGui import QDesktopServices

import core

MTX_API = "http://127.0.0.1:9997/v3/paths/list"
MTX_RTMP = "rtmp://127.0.0.1:1935"

PLATFORMS = {
    "custom":   ("自定义RTMP后台", "自定义推流地址", None),
    "douyin":   ("抖音", "抖音推流地址", "抖音推流码"),
    "bilibili": ("B站", "B站推流地址", "B站推流码"),
}


# ---------------------------------------------------------------------------
# 通用进程封装
# ---------------------------------------------------------------------------
class Proc(QObject):
    log = Signal(str, str, str)   # level, source, msg
    started_ok = Signal(str)      # source
    failed = Signal(str, str)     # source, msg
    exited_ok = Signal(str, int)  # source, code

    def __init__(self, source, parent=None):
        super().__init__(parent)
        self.source = source
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        # 无控制台 GUI 下不弹黑窗：CREATE_NO_WINDOW = 0x08000000
        try:
            self.proc.setCreateProcessArgumentsModifier(self._hide_console)
        except Exception:
            pass
        self._buf = ""
        self.proc.readyReadStandardOutput.connect(self._on_read)
        self.proc.errorOccurred.connect(self._on_error)
        self.proc.stateChanged.connect(self._on_state)
        self._started_seen = False

    @staticmethod
    def _hide_console(params):
        try:
            params.flags = int(params.flags) | 0x08000000
        except Exception:
            pass

    def start(self, exe, args=None, cwd=None):
        args = args or []
        if cwd:
            self.proc.setWorkingDirectory(cwd)
        self.proc.setProgram(exe)
        self.proc.setArguments(args)
        self.log.emit("info", self.source, "启动：%s %s" % (exe, " ".join(args)))
        self.proc.start()

    def _on_read(self):
        data = bytes(self.proc.readAllStandardOutput())
        text = data.decode("utf-8", errors="replace")
        self._buf += text
        # ffmpeg 进度用 \r 刷新，需要同时按 \r、\n 切分
        chunks = re.split(r"[\r\n]+", self._buf)
        self._buf = chunks[-1]
        for line in chunks[:-1]:
            line = line.strip()
            if line:
                self.handle_line(line)

    def handle_line(self, line):
        self.log.emit("info", self.source, line)

    def _on_error(self, err):
        if err == QProcess.FailedToStart:
            self.failed.emit(self.source, "程序无法启动（文件缺失或被杀毒拦截）。")
        else:
            self.log.emit("warn", self.source, "进程错误：%s" % err)

    def _on_state(self, state):
        if state == QProcess.Starting:
            return
        if state == QProcess.Running:
            if not self._started_seen:
                self._started_seen = True
                self.started_ok.emit(self.source)
        elif state == QProcess.NotRunning:
            code = self.proc.exitCode()
            self.exited_ok.emit(self.source, code)

    def is_running(self):
        return self.proc.state() != QProcess.NotRunning

    def stop(self, kill_ms=1800):
        if not self.is_running():
            return
        try:
            self.proc.terminate()
        except Exception:
            pass
        QTimer.singleShot(kill_ms, self._force_kill)

    def hard_stop(self):
        """立即强杀（退出程序时使用，确保不留孤儿进程）。"""
        try:
            if self.is_running():
                self.proc.kill()
        except Exception:
            pass

    def _force_kill(self):
        self.hard_stop()


# ---------------------------------------------------------------------------
# MediaMTX
# ---------------------------------------------------------------------------
class MediaMTX(Proc):
    rtmp_ready = Signal()
    hls_ready = Signal()
    webrtc_ready = Signal()
    path_ready = Signal(str)
    port_error = Signal(str)

    def __init__(self, parent=None):
        super().__init__("MediaMTX", parent)
        self.rtmp_listener = False
        self.ready_paths = set()

    def reset(self):
        self.rtmp_listener = False
        self.ready_paths = set()

    def start_mtx(self):
        exe = core.find_mediamtx()
        if not exe:
            self.failed.emit(self.source,
                             "未找到 mediamtx.exe（应在工具目录的 mediamtx 文件夹内）。")
            return
        self.reset()
        self.start(exe, [], cwd=os.path.dirname(exe))

    def handle_line(self, line):
        low = line.lower()
        # 监听端口（兼容新旧两种格式：
        #   旧：listener opened on :1935
        #   新：[RTMP] started with listener on :1935 (TCP/RTMP)
        #   新：[RTSP] started with listeners on :8554 (...), :8000 (...)
        if "listener opened on" in low or "started with listener" in low:
            ports = re.findall(r":(\d+)\s*(?:\(|$|,| )", low)
            labels = {"1935": "RTMP 收流", "8888": "HLS 播放", "8889": "WebRTC 播放"}
            if "1935" in ports:
                self.rtmp_listener = True
                self.rtmp_ready.emit()
            for port in ports:
                if port in labels:
                    self.log.emit("ok", "MediaMTX", "%s端口已就绪 :%s" % (labels[port], port))
                elif port in ("8554", "8000", "8001", "8890", "8189", "8002", "9997"):
                    pass  # 其他端口不打扰用户
                else:
                    self.log.emit("info", "MediaMTX", "端口已监听 :%s" % port)
            return
        # 流就绪（path ready）
        m = re.search(r"path '([^']+)' is ready", line)
        if not m:
            m = re.search(r"path '([^']+)' (?:is )?ready", line)
        if m:
            name = m.group(1)
            if name not in self.ready_paths:
                self.ready_paths.add(name)
                self.path_ready.emit(name)
                self.log.emit("ok", "MediaMTX", "收到推流：path %s is ready" % name)
            return
        # 端口占用/绑定失败
        if ("address already in use" in low or "bind" in low and "error" in low
                or "listen tcp" in low and "error" in low or "one or more listeners failed" in low):
            self.port_error.emit(line)
            self.log.emit("error", "MediaMTX", "端口绑定失败：" + line)
            return
        if "ERR" in line or " ERROR " in line:
            self.log.emit("warn", "MediaMTX", line)
        elif "is publishing" in line or "publisher" in low or "reader started" in low:
            self.log.emit("ok", "MediaMTX", line)
        else:
            self.log.emit("info", "MediaMTX", line)


# ---------------------------------------------------------------------------
# MediaMTX API
# ---------------------------------------------------------------------------
def fetch_paths(timeout=1.5):
    """返回 (items, error)。items 为 [{name, ready, ...}]。"""
    try:
        with urllib.request.urlopen(MTX_API, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("items", []), None
    except Exception as e:
        return [], str(e)


def pick_ps5_path(items):
    ready = [it.get("name", "") for it in items if it.get("ready")]
    for n in ready:
        if n.startswith("app/"):
            return n
    return ready[0] if ready else ""


def build_watch_urls(path):
    return {
        "webrtc_page": "http://127.0.0.1:8889/%s/" % path,
        "hls_page": "http://127.0.0.1:8888/%s/" % path,
        "rtmp": "rtmp://127.0.0.1:1935/%s" % path,
        "hls": "http://127.0.0.1:8888/%s/index.m3u8" % path,
    }


# ---------------------------------------------------------------------------
# 转推管理
# ---------------------------------------------------------------------------
class RelayManager(QObject):
    log = Signal(str, str, str)
    stage = Signal(str)              # idle / waiting / pushing / done / error
    stats = Signal(dict)             # frame fps bitrate time
    error = Signal(str, str)         # device, message
    started_ok = Signal()
    finished = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.proc = None
        self.platform = "custom"
        self.target = ""
        self.path = ""
        self.wait_timer = QTimer(self)
        self.wait_timer.setInterval(2000)
        self.wait_timer.timeout.connect(self._poll_path)
        self.wait_deadline = 0
        self.last_frame = -1
        self.last_frame_time = 0
        self.stall_warned = False

    def is_active(self):
        return self.proc is not None and self.proc.is_running()

    def is_waiting(self):
        return self.wait_timer.isActive()

    def stop(self):
        self.wait_timer.stop()
        if self.proc is not None:
            self.proc.hard_stop()
            self.proc = None
        self.stage.emit("idle")

    # ---------- 配置校验 ----------
    def build_target(self, cfg, platform):
        name, url_key, code_key = PLATFORMS[platform]
        if code_key:
            url = (cfg.get(url_key, "") or "").strip().rstrip("/")
            key = (cfg.get(code_key, "") or "").strip().lstrip("/")
            target = (url + "/" + key) if (url and key) else url
        else:
            target = (cfg.get(url_key, "") or "").strip()
        return target

    def start_relay(self, cfg, platform, path=None):
        if self.is_active() or self.is_waiting():
            return
        ffmpeg = core.find_ffmpeg()
        if not ffmpeg:
            self.error.emit("本机电脑",
                "未找到 ffmpeg，无法转推。请安装 ffmpeg 并加入系统 PATH，"
                "或把 ffmpeg.exe 放到工具目录的 ffmpeg 文件夹内。")
            self.stage.emit("error")
            return

        target = self.build_target(cfg, platform)
        plat_name = PLATFORMS[platform][0]
        if not target:
            if platform == "custom":
                self.error.emit("配置", "还没有填写【自定义推流地址】，请到【设置】里粘贴完整 RTMP URL（rtmp:// 开头）。")
            else:
                self.error.emit("配置", "还没有在【设置】里填全%s的推流地址和推流码。" % plat_name)
            self.stage.emit("error")
            return
        if not target.lower().startswith("rtmp"):
            self.error.emit("配置", "目标地址必须以 rtmp:// 或 rtmps:// 开头，当前为：%s" % target)
            self.stage.emit("error")
            return

        self.platform = platform
        self.target = target
        self.ffmpeg = ffmpeg
        self.reencode = (cfg.get("重编码", "否").strip() in ("是", "yes", "y", "1", "true"))
        self.last_frame = -1
        self.stall_warned = False

        if path:
            self.path = path
            self._launch_ffmpeg()
        else:
            self.log.emit("info", "转推", "正在等待 PS5 推流到达本机（请确认 PS5 已开始 Twitch 直播）…")
            self.stage.emit("waiting")
            self.wait_deadline = time.time() + 120
            self.wait_timer.start()

    def _poll_path(self):
        items, _ = fetch_paths(timeout=1.5)
        path = pick_ps5_path(items)
        if path:
            self.wait_timer.stop()
            self.path = path
            self._launch_ffmpeg()
            return
        if time.time() > self.wait_deadline:
            self.wait_timer.stop()
            self.stage.emit("error")
            self.error.emit("PS5主机",
                "120 秒内没收到 PS5 推流。请按顺序检查：\n"
                "① 一键启动已运行，DNS 服务已监听；\n"
                "② PS5 已经对 Twitch 开始直播，且第 3 关出现【劫持成功】；\n"
                "③ MediaMTX 已出现 path app/xxx is ready；\n"
                "④ PS5 与电脑是否连同一个路由器、加速器是否正常。")

    def _launch_ffmpeg(self):
        source = "%s/%s" % (MTX_RTMP, self.path)
        self.log.emit("ok", "转推", "已捕获 PS5 本地流：%s" % source)
        self.log.emit("ok", "转推", "目标：%s；编码方式：%s" % (
            PLATFORMS[self.platform][0],
            "重新编码（兼容性好、占CPU）" if self.reencode else "直接转发（-c copy，省CPU）"))

        if self.reencode:
            args = ["-nostdin", "-i", source,
                    "-c:v", "libx264", "-preset", "veryfast", "-b:v", "4000k",
                    "-c:a", "aac", "-b:a", "128k", "-f", "flv", self.target]
        else:
            args = ["-nostdin", "-i", source, "-c", "copy", "-f", "flv", self.target]

        self.proc = Proc("转推", self)
        self.proc.log.connect(self._on_proc_log)
        self.proc.failed.connect(self._on_proc_failed)
        self.proc.exited_ok.connect(self._on_proc_exited)
        self.proc.start(self.ffmpeg, args)
        self.stage.emit("pushing")
        self.started_ok.emit()

    # 隐藏推流码
    def _safe_target(self):
        parts = self.target.split("/")
        if len(parts) > 3:
            return "/".join(parts[:3]) + "/****（推流码已隐藏）"
        return self.target

    def _on_proc_log(self, level, source, line):
        low = line.lower()
        # 进度
        m = re.search(r"frame=\s*(\d+)", line)
        if m:
            frame = int(m.group(1))
            fps = re.search(r"fps=\s*([\d.]+)", line)
            bitrate = re.search(r"bitrate=\s*([^\s]+(?:\s*[kKmM]?bits/s)?)", line)
            t = re.search(r"time=\s*(\d+:\d+:\d+[.:]\d+)", line)
            now = time.time()
            if frame != self.last_frame:
                self.last_frame = frame
                self.last_frame_time = now
                self.stats.emit({
                    "frame": frame,
                    "fps": fps.group(1) if fps else "?",
                    "bitrate": bitrate.group(1) if bitrate else "?",
                    "time": t.group(1) if t else "?",
                })
            else:
                # 连续 15 秒帧数不动：后台可能黑屏/卡住
                if frame > 0 and not self.stall_warned and now - self.last_frame_time > 15:
                    self.stall_warned = True
                    self.log.emit("warn", "转推", "已 15 秒没有新画面帧；若后台黑屏，请到设置把【重编码】改为“是”后重试。")
            return

        # 典型错误归因
        if "connection refused" in low:
            self.log.emit("error", "转推", "连接被拒绝：本机 MediaMTX 未收到流或未启动。")
            self.error.emit("本机电脑", "ffmpeg 连不上本机 MediaMTX（1935）。请确认一键启动已运行、第 4 关已收到画面。")
        elif "connection reset by peer" in low or "broken pipe" in low:
            self.log.emit("error", "转推", "推流目标中断了连接（多半是推流地址/推流码错误或过期）。")
            self.error.emit("推流后台/平台", "推流被后台重置：请核对推流地址与推流码是否正确、是否过期；抖音/B站每次开播推流码会变。")
        elif "404" in line or "not found" in low:
            self.log.emit("error", "转推", "后台返回 404：推流路径/推流码有误。")
            self.error.emit("推流后台/平台", "后台返回 404，通常是推流地址或推流码填错/过期，请重新获取。")
        elif "i/o error" in low or "immediate exit" in low or "error number" in low:
            self.log.emit("error", "转推", line)
            self.error.emit("推流后台/平台", "与后台之间出现 I/O 错误：检查网络/加速器、推流地址是否有效；若后台黑屏，可把【重编码】改为“是”。")
        elif "invalid data" in low or "invalid argument" in low or "could not find" in low:
            self.log.emit("error", "转推", line)
            self.error.emit("本机电脑", "ffmpeg 无法处理该流：请在设置里把【重编码】改为“是”后重试。")
        elif "error" in low:
            self.log.emit("warn", "转推", line)
        else:
            self.log.emit("info", "转推", line)

    def _on_proc_failed(self, source, msg):
        self.stage.emit("error")
        self.error.emit("本机电脑", "ffmpeg 启动失败：" + msg)

    def _on_proc_exited(self, source, code):
        self.proc = None
        if code == 0:
            self.stage.emit("done")
            self.log.emit("ok", "转推", "转推已正常结束。")
        else:
            self.stage.emit("error")
            self.log.emit("error", "转推", "ffmpeg 退出，退出码 %s。" % code)
            self.error.emit("推流后台/平台",
                "ffmpeg 异常退出（退出码 %s）。常见原因：推流地址/推流码错误或过期、后台不支持直接转发"
                "（到设置把【重编码】改为“是”）、网络中断。" % code)
        self.finished.emit(code)
