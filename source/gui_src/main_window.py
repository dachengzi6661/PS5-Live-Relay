# -*- coding: utf-8 -*-
"""主窗口（玻璃质感版）：无边框 GUI，整合启动/停止/收流/劫持/转推/监看/配置/诊断/日志。

设计要点
--------
- 顶部导航栏：玻璃质感 + 发丝分隔线；左侧标题、正中分段控件、右侧窗口按钮，
  左右等宽容器保证分段控件严格居中（居中对称）。
- 内容区：超大面积留白、卡片间距 22px、单列居中构图。
- 主按钮为品牌蓝胶囊；次按钮为中性玻璃胶囊；其余元素黑白灰。
- 电影级产品大图置于「首选 DNS」横幅右侧（预渲染圆角，见 make_assets.py）。
"""
import os
import sys
import time
import ctypes

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QPoint, QEvent
from PySide6.QtGui import QIcon, QFont, QAction, QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QGridLayout, QStackedWidget, QLineEdit, QComboBox, QCheckBox,
    QPlainTextEdit, QScrollArea, QListWidget, QListWidgetItem,
    QTreeWidget, QTreeWidgetItem, QMessageBox, QSystemTrayIcon, QMenu, QFileDialog,
    QSizePolicy, QGraphicsOpacityEffect, QGraphicsDropShadowEffect)

import core
import theme
from theme import COLORS, DEVICE_COLORS, R_SHELL, R_CARD
from widgets import (StateIcon, ServicePill, DeviceChip, GateCard, ProgressBar,
                     TaskThread, LogConsole, WinButton, PillButton, SegButton,
                     ToggleSwitch, tracking)
import wineffects
from dns_engine import DnsEngine
from workers import (MediaMTX, RelayManager, fetch_paths, pick_ps5_path,
                     build_watch_urls, PLATFORMS, MTX_API)
from diagnostics import (run_preflight, evaluate, AppState, GATES, GATE_HELP,
                         DEVICES, OK, WARN, ERROR)

NAV_ITEMS = [("总览", 0), ("监看", 1), ("设置", 2), ("诊断", 3), ("日志", 4)]


def elide(s, n=60):
    s = str(s)
    return s if len(s) <= n else s[:n] + "…"


def asset_pixmap(name, w=None, h=None):
    """从 assets 读图；带 2x devicePixelRatio，保证 HiDPI 下细节锐利。"""
    path = core.resource_path("assets", name)
    if not os.path.exists(path):
        return None
    pm = QPixmap(path)
    if pm.isNull():
        return None
    if pm.width() >= 2 * (w or 0) or pm.height() >= 2 * (h or 0):
        pm.setDevicePixelRatio(2.0)
    return pm


class Toast(QLabel):
    """轻量提示：白玻璃胶囊 + 柔和投影。"""

    def __init__(self, parent):
        super().__init__(parent)
        self.eff = QGraphicsOpacityEffect(self)
        self.eff.setOpacity(0)
        self.setGraphicsEffect(self.eff)
        self.anim = QPropertyAnimation(self.eff, b"opacity", self)
        self.anim.setDuration(240)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._hide)
        self._style(COLORS["accent"])
        self.hide()

    def _style(self, dot):
        self.setStyleSheet(
            "background:%s;color:%s;border:1px solid %s;border-radius:18px;"
            "padding:11px 22px;font-size:13px;font-weight:500;"
            % (COLORS["pill_bg"], COLORS["text"], COLORS["pill_edge"]))
        self._dot = dot

    def show_msg(self, msg, level="info"):
        col = {"ok": COLORS["ok"], "error": COLORS["error"],
               "warn": COLORS["warn"], "info": COLORS["accent"]}.get(level, COLORS["accent"])
        self._style(col)
        self.setText("●  " + msg)
        self.adjustSize()
        self._reposition()
        self.anim.stop()
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()
        self.show()
        self.raise_()
        self._timer.start(3600)

    def _reposition(self):
        if self.parent() is None:
            return
        pw = self.parent().width()
        ph = self.parent().height()
        self.move((pw - self.width()) // 2, ph - self.height() - 36)

    def _hide(self):
        self.anim.stop()
        self.anim.setStartValue(self.eff.opacity())
        self.anim.setEndValue(0.0)
        self.anim.start()


class MainWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setObjectName("MainWindow")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowSystemMenuHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(1180, 820)
        self.setMinimumSize(1020, 720)

        self.cfg = core.load_config()
        self.state = AppState()
        self.current_ip = ""
        self.current_mode = ""
        self._prev_frame = -1
        self._stopping = False

        # 引擎
        self.dns = DnsEngine(self)
        self.mtx = MediaMTX(self)
        self.relay = RelayManager(self)
        self._fw_thread = None
        self._preflight_thread = None

        self._build_ui()
        self._wire_signals()
        self._load_settings()
        for b in self.findChildren(QPushButton):
            b.setCursor(Qt.PointingHandCursor)
        for b in self.findChildren(WinButton):
            b.setCursor(Qt.ArrowCursor)
        self.refresh_monitor()

        # 定时：API 轮询 + 5 关刷新
        self.poll = QTimer(self)
        self.poll.setInterval(1500)
        self.poll.timeout.connect(self._tick)
        self.poll.start()

        # 托盘
        self._build_tray()

        # 后台检测 IP
        self._detect_ip_thread = TaskThread(core.detect_gateway_ip, self.cfg.get("网关IP", ""))
        self._detect_ip_thread.result.connect(self._on_ip_detected)
        self._detect_ip_thread.start()

        self.log("info", "系统", "程序已就绪。点击【一键启动】开始；首次运行请允许 UAC 管理员授权。")
        self.refresh_gates()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        # 外壳铺满整个窗口（不留透明外框）——无边框窗口一旦留出透明边距，
        # 在部分系统/远程桌面下会被渲染成黑色边框，这里直接去掉。
        central = QWidget()
        central.setObjectName("MainWindow")
        self.central = central
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        shell = QFrame()
        shell.setObjectName("GlassShell")
        self.shell = shell
        outer.addWidget(shell)

        root = QVBoxLayout(shell)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._top_nav())

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(28, 20, 28, 24)
        cl.setSpacing(0)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._tab_dashboard())
        self.stack.addWidget(self._tab_monitor())
        self.stack.addWidget(self._tab_settings())
        self.stack.addWidget(self._tab_diagnostics())
        self.stack.addWidget(self._tab_logs())
        cl.addWidget(self.stack, 1)
        root.addWidget(content, 1)

        self.set_page(0)
        self.toast = Toast(shell)

    # ---------------------------------------------------------- 顶部导航
    def _top_nav(self):
        bar = QFrame()
        bar.setObjectName("TopNav")
        bar.setFixedHeight(58)
        g = QGridLayout(bar)
        g.setContentsMargins(20, 0, 12, 0)
        g.setHorizontalSpacing(10)

        # 左：品牌区（固定最小宽度，与右侧等宽 → 中间分段控件严格居中）
        left = QWidget()
        left.setMinimumWidth(268)
        lh = QHBoxLayout(left)
        lh.setContentsMargins(0, 0, 0, 0)
        lh.setSpacing(10)
        mark = QLabel()
        mark.setFixedSize(22, 22)
        try:
            pm = asset_pixmap("app.png")
            if pm is not None:
                mark.setPixmap(pm.scaled(22, 22, Qt.KeepAspectRatio,
                                         Qt.SmoothTransformation))
        except Exception:
            pass
        title = QLabel("PS5 直播推流助手")
        title.setObjectName("NavTitle")
        left_sub = QLabel("直播中转站")
        left_sub.setObjectName("NavMark")
        lh.addWidget(mark)
        lh.addWidget(title)
        lh.addWidget(left_sub)
        lh.addStretch()

        # 中：分段控件（玻璃质感轨道 + 白色选中胶囊）
        seg = QFrame()
        seg.setObjectName("SegTrack")
        sl = QHBoxLayout(seg)
        sl.setContentsMargins(3, 3, 3, 3)
        sl.setSpacing(2)
        self.nav_btns = []
        for name, idx in NAV_ITEMS:
            b = SegButton(name)
            b.clicked.connect(lambda _=False, i=idx: self.set_page(i))
            sl.addWidget(b)
            self.nav_btns.append(b)

        # 右：窗口按钮（与左侧等宽）
        right = QWidget()
        right.setMinimumWidth(268)
        rh = QHBoxLayout(right)
        rh.setContentsMargins(0, 0, 0, 0)
        rh.setSpacing(2)
        rh.addStretch()
        self.btn_theme = WinButton("theme")
        self.btn_theme.setToolTip("切换 白天 / 黑夜 模式")
        self.btn_theme.clicked.connect(self.toggle_theme)
        self.btn_min = WinButton("min")
        self.btn_min.setToolTip("最小化")
        self.btn_min.clicked.connect(self.showMinimized)
        self.btn_max = WinButton("max")
        self.btn_max.setToolTip("最大化 / 还原")
        self.btn_max.clicked.connect(self._toggle_max)
        self.btn_close = WinButton("close")
        self.btn_close.setToolTip("关闭")
        self.btn_close.clicked.connect(self._on_close)
        for b in (self.btn_theme, self.btn_min, self.btn_max, self.btn_close):
            rh.addWidget(b)

        g.addWidget(left, 0, 0)
        g.addWidget(seg, 0, 1, Qt.AlignCenter)
        g.addWidget(right, 0, 2)
        g.setColumnStretch(0, 1)
        g.setColumnStretch(1, 0)
        g.setColumnStretch(2, 1)

        self._drag_pos = None
        return bar

    def set_page(self, i):
        if hasattr(self, "stack"):
            self.stack.setCurrentIndex(i)
        for k, b in enumerate(getattr(self, "nav_btns", [])):
            b.setChecked(k == i)

    def current_page(self):
        return self.stack.currentIndex() if hasattr(self, "stack") else 0

    def _toggle_max(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def changeEvent(self, e):
        if e.type() == QEvent.WindowStateChange and hasattr(self, "btn_max"):
            self.btn_max.set_maximized(self.isMaximized())
        super().changeEvent(e)

    # 说明：这里刻意不启用系统级亚克力模糊。wineffects.enable_acrylic() 会调用
    # DwmExtendFrameIntoClientArea 把整个客户区变成 DWM 玻璃区，一旦亚克力不可用
    # （部分显卡驱动 / 远程桌面 / Win10），未绘制区域会直接渲染成黑色，表现为
    # 窗口四周出现一圈粗黑边。玻璃质感观感改由 QSS 的半透明层 + 发丝高光承担。

    def toggle_theme(self):
        new_mode = "黑夜" if theme.active_mode() == "白天" else "白天"
        self.cfg["主题"] = new_mode
        try:
            core.save_config(self.cfg)
        except Exception:
            pass
        theme.apply_theme(self.app, self, new_mode)
        self.toast.show_msg("已切换到%s模式" % new_mode, "ok")

    def retheme(self):
        """日夜切换后：刷新自绘控件、投影、按钮控件级样式。"""
        for w in self.findChildren(DeviceChip):
            w.retheme()
        for w in self.findChildren(ServicePill):
            w.retheme()
        for w in self.findChildren(GateCard):
            w.retheme()
        for w in self.findChildren(WinButton):
            w.update()
        if hasattr(self, "log_view"):
            self.log_view.retheme()
        for w in self.findChildren(QWidget):
            w.update()
        try:
            self.refresh_gates()
        except Exception:
            pass

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and e.position().y() < 58:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None
        super().mouseReleaseEvent(e)

    # ------------------------------------------------------------------ 总览
    def _tab_dashboard(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(2, 2, 8, 2)
        v.setSpacing(22)

        # ---------- Hero：居中对称，超大留白 ----------
        hero = QFrame()
        hero.setObjectName("HeroCard")
        hero.setMinimumHeight(250)
        hv = QVBoxLayout(hero)
        hv.setContentsMargins(48, 40, 48, 38)
        hv.setSpacing(12)
        hv.setAlignment(Qt.AlignHCenter)

        kicker = QLabel("实 时 状 态")
        kicker.setObjectName("HeroKicker")
        kicker.setAlignment(Qt.AlignCenter)
        tracking(kicker, 2.0)

        self.hero_status = QLabel("未启动")
        self.hero_status.setObjectName("H1")
        self.hero_status.setAlignment(Qt.AlignCenter)
        self.hero_status.setStyleSheet("color:%s;" % COLORS["text"])
        tracking(self.hero_status, -0.8)

        self.hero_sub = QLabel("点击【一键启动】，开启收流与 DNS 劫持；PS5 首选 DNS 填下方地址")
        self.hero_sub.setObjectName("Sub")
        self.hero_sub.setAlignment(Qt.AlignCenter)
        self.hero_sub.setWordWrap(True)

        self.btn_start = PillButton("一键启动", "primary")
        self.btn_start.setMinimumWidth(176)
        self.btn_start.clicked.connect(self.start_all)
        self.btn_stop = PillButton("一键停止", "ghost")
        self.btn_stop.setMinimumWidth(176)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_all)

        btns = QHBoxLayout()
        btns.setSpacing(14)
        btns.addStretch()
        btns.addWidget(self.btn_start)
        btns.addWidget(self.btn_stop)
        btns.addStretch()

        hv.addWidget(kicker)
        hv.addWidget(self.hero_status)
        hv.addWidget(self.hero_sub)
        hv.addSpacing(14)
        hv.addLayout(btns)
        v.addWidget(hero)

        # ---------- 首选 DNS（居中对称，无配图） ----------
        band = QFrame()
        band.setObjectName("Card")
        bh = QVBoxLayout(band)
        bh.setContentsMargins(40, 30, 40, 34)
        bh.setSpacing(10)
        bh.addStretch()

        l1 = QLabel("在 PS5 上把【首选 DNS】填成这个地址")
        l1.setObjectName("Muted")
        l1.setAlignment(Qt.AlignCenter)
        l1.setWordWrap(True)
        self.lbl_ip = QLabel("检测中…")
        self.lbl_ip.setObjectName("BigIp")
        self.lbl_ip.setAlignment(Qt.AlignCenter)
        tracking(self.lbl_ip, -0.8)
        l2 = QLabel("备选 DNS 留空（0.0.0.0）；IP / 掩码 / 网关照抄加速器")
        l2.setObjectName("Faint")
        l2.setAlignment(Qt.AlignCenter)
        l2.setWordWrap(True)
        self.btn_copy_ip = PillButton("复制 IP", "chip")
        self.btn_copy_ip.setFixedWidth(116)
        self.btn_copy_ip.clicked.connect(self._copy_ip)

        bh.addWidget(l1)
        bh.addWidget(self.lbl_ip)
        bh.addWidget(l2)
        bh.addSpacing(8)
        bh.addWidget(self.btn_copy_ip, 0, Qt.AlignHCenter)
        bh.addStretch()
        v.addWidget(band)

        # ---------- 开播 5 关 ----------
        gcard = QFrame()
        gcard.setObjectName("Card")
        gv = QVBoxLayout(gcard)
        gv.setContentsMargins(24, 22, 24, 24)
        gv.setSpacing(16)
        gt = QHBoxLayout()
        gtitle = self._h3("开播 5 关检测（一关一关过，卡点即停）")
        gt.addWidget(gtitle)
        gt.addStretch()
        self.lbl_guide = QLabel("点关卡卡片可查看该关卡的排查方法")
        self.lbl_guide.setObjectName("Faint")
        gt.addWidget(self.lbl_guide)
        gv.addLayout(gt)
        grows = QHBoxLayout()
        grows.setSpacing(8)
        self.gate_cards = []
        for i, gate in enumerate(GATES, start=1):
            c = GateCard(i, gate)
            c.clicked.connect(self._on_gate_click)
            self.gate_cards.append(c)
            grows.addWidget(c, 1)
            if i < len(GATES):
                arrow = QLabel("›")
                arrow.setObjectName("Faint")
                arrow.setAlignment(Qt.AlignCenter)
                arrow.setFixedWidth(12)
                grows.addWidget(arrow)
        gv.addLayout(grows)

        # 诊断结论卡
        self.diag = QFrame()
        self.diag.setObjectName("PanelCard")
        dg = QVBoxLayout(self.diag)
        dg.setContentsMargins(20, 16, 20, 18)
        dg.setSpacing(8)
        self.diag_top = QHBoxLayout()
        self.diag_chip = DeviceChip("pc")
        self.diag_title = QLabel("")
        self.diag_title.setStyleSheet("font-weight:600;font-size:14px;")
        self.diag_top.addWidget(self.diag_chip)
        self.diag_top.addWidget(self.diag_title)
        self.diag_top.addStretch()
        dg.addLayout(self.diag_top)
        self.diag_body = QLabel("")
        self.diag_body.setWordWrap(True)
        self.diag_body.setStyleSheet("color:%s;" % COLORS["text"])
        dg.addWidget(self.diag_body)
        self.diag_tips = QLabel("")
        self.diag_tips.setWordWrap(True)
        self.diag_tips.setStyleSheet("color:%s;font-size:12px;" % COLORS["muted"])
        self.diag_tips.setTextFormat(Qt.RichText)
        dg.addWidget(self.diag_tips)
        self.diag.hide()
        gv.addWidget(self.diag)
        v.addWidget(gcard)

        # ---------- 服务状态 / 转推 ----------
        srow = QHBoxLayout()
        srow.setSpacing(22)
        svc_card = QFrame()
        svc_card.setObjectName("Card")
        sv = QVBoxLayout(svc_card)
        sv.setContentsMargins(24, 22, 24, 22)
        sv.setSpacing(12)
        sv.addWidget(self._h3("服务状态"))
        self.pill_mtx = ServicePill("MediaMTX 收流")
        self.pill_dns = ServicePill("DNS 劫持")
        self.pill_fw = ServicePill("防火墙")
        for pill in (self.pill_mtx, self.pill_dns, self.pill_fw):
            sv.addWidget(pill)
        sv.addStretch()
        srow.addWidget(svc_card, 1)

        relay_card = QFrame()
        relay_card.setObjectName("Card")
        rv = QVBoxLayout(relay_card)
        rv.setContentsMargins(24, 22, 24, 22)
        rv.setSpacing(12)
        rt = QHBoxLayout()
        rt.addWidget(self._h3("转推到后台"))
        rt.addStretch()
        self.cmb_platform = QComboBox()
        self.cmb_platform.setMinimumWidth(150)
        for key, (name, _, _) in PLATFORMS.items():
            self.cmb_platform.addItem(name, key)
        self.cmb_platform.currentIndexChanged.connect(self._on_platform_changed)
        rt.addWidget(self.cmb_platform)
        rv.addLayout(rt)
        self.btn_relay = PillButton("开始转推", "primary")
        self.btn_relay.clicked.connect(self._on_relay_clicked)
        rv.addWidget(self.btn_relay)
        self.lbl_relay_stats = QLabel("未开始转推")
        self.lbl_relay_stats.setObjectName("Muted")
        self.lbl_relay_stats.setWordWrap(True)
        rv.addWidget(self.lbl_relay_stats)
        self.lbl_relay_hint = QLabel("收到 PS5 画面后再点；frame 持续增长即成功")
        self.lbl_relay_hint.setObjectName("Faint")
        self.lbl_relay_hint.setWordWrap(True)
        rv.addWidget(self.lbl_relay_hint)
        rv.addStretch()
        srow.addWidget(relay_card, 1)
        v.addLayout(srow)

        # ---------- 快捷操作 ----------
        qa = QFrame()
        qa.setObjectName("Card")
        qv = QVBoxLayout(qa)
        qv.setContentsMargins(24, 22, 24, 22)
        qv.setSpacing(14)
        qv.addWidget(self._h3("快捷操作"))
        qgrid = QGridLayout()
        qgrid.setHorizontalSpacing(10)
        qgrid.setVerticalSpacing(10)
        quick = [
            ("打开 WebRTC 监看（低延迟）", self.watch_webrtc),
            ("打开 HLS 监看（兼容）", self.watch_hls),
            ("复制 RTMP 拉流地址", self.copy_rtmp),
            ("复制 HLS 拉流地址", self.copy_hls),
            ("刷新在线流", self.refresh_monitor),
            ("打开工具目录", self.open_folder),
        ]
        for i, (text, fn) in enumerate(quick):
            b = PillButton(text, "chip")
            b.clicked.connect(fn)
            qgrid.addWidget(b, i // 3, i % 3)
        qgrid.setColumnStretch(3, 1)
        qv.addLayout(qgrid)
        v.addWidget(qa)

        # ---------- 5 步速览 ----------
        guide = QFrame()
        guide.setObjectName("Card")
        gv2 = QVBoxLayout(guide)
        gv2.setContentsMargins(24, 22, 24, 24)
        gv2.setSpacing(10)
        gv2.addWidget(self._h3("每次开播固定 5 步"))
        steps = ("① 电脑开加速器主机加速　② 点【一键启动】（UAC 点“是”）　"
                 "③ PS5 进游戏 → 创建键 → 直播 → Twitch → 开始直播　"
                 "④ 打开 WebRTC 监看看到画面（黑屏换 HLS）　⑤ 点【开始转推】，后台确认画面")
        sl = QLabel(steps)
        sl.setWordWrap(True)
        sl.setStyleSheet("color:%s;line-height:1.7;" % COLORS["muted"])
        gv2.addWidget(sl)
        v.addWidget(guide)

        v.addStretch()
        scroll.setWidget(w)
        return scroll

    # ------------------------------------------------------------------ 监看
    def _tab_monitor(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(2, 2, 8, 2)
        v.setSpacing(22)

        head = QFrame()
        head.setObjectName("Card")
        hv = QVBoxLayout(head)
        hv.setContentsMargins(28, 24, 28, 24)
        hv.setSpacing(10)
        hv.addWidget(self._h2("本地监看 / 拉流地址"))
        tip = QLabel("MediaMTX 收到的在线流会自动出现在这里；网页用于本地监看，"
                     "拉流地址（RTMP / HLS）填给 OBS / 直播伴侣当「网络流素材」，"
                     "不要把网页地址填进去。")
        tip.setObjectName("Muted")
        tip.setWordWrap(True)
        hv.addWidget(tip)
        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.btn_mon_refresh = PillButton("刷新在线流", "chip")
        self.btn_mon_refresh.clicked.connect(self.refresh_monitor)
        self.btn_mon_webrtc = PillButton("WebRTC 监看（约 1 秒）", "chip")
        self.btn_mon_webrtc.clicked.connect(self.watch_webrtc)
        self.btn_mon_hls = PillButton("HLS 监看（3-8 秒，黑屏用它）", "chip")
        self.btn_mon_hls.clicked.connect(self.watch_hls)
        for b in (self.btn_mon_refresh, self.btn_mon_webrtc, self.btn_mon_hls):
            bar.addWidget(b)
        bar.addStretch()
        hv.addLayout(bar)
        v.addWidget(head)

        lcard = QFrame()
        lcard.setObjectName("Card")
        lv = QVBoxLayout(lcard)
        lv.setContentsMargins(24, 22, 24, 24)
        lv.setSpacing(12)
        lv.addWidget(self._h3("在线流"))
        self.list_paths = QListWidget()
        self.list_paths.setMinimumHeight(130)
        lv.addWidget(self.list_paths)
        v.addWidget(lcard)

        # URL 卡片
        self.url_box = QFrame()
        self.url_box.setObjectName("Card")
        uv = QVBoxLayout(self.url_box)
        uv.setContentsMargins(24, 22, 24, 24)
        uv.setSpacing(14)
        uv.addWidget(self._h3("拉流地址"))
        self.url_rows = {}
        for key, name in [("webrtc_page", "WebRTC 观看页"), ("hls_page", "HLS 观看页"),
                          ("rtmp", "RTMP 拉流（填直播伴侣）"), ("hls", "HLS 拉流（填 OBS）")]:
            row = QHBoxLayout()
            row.setSpacing(12)
            lab = QLabel(name)
            lab.setFixedWidth(190)
            lab.setObjectName("Muted")
            val = QLineEdit()
            val.setReadOnly(True)
            val.setPlaceholderText("PS5 开播后自动生成")
            btn = PillButton("复制", "chip")
            btn.setFixedWidth(78)
            btn.clicked.connect(lambda _=False, k=key: self._copy_url(k))
            row.addWidget(lab)
            row.addWidget(val, 1)
            row.addWidget(btn)
            uv.addLayout(row)
            self.url_rows[key] = val
        self.btn_mon_autocopy = PillButton("一键复制 RTMP 拉流地址", "primary")
        self.btn_mon_autocopy.clicked.connect(self.copy_rtmp)
        self.btn_mon_save = PillButton("把 4 个地址另存为 stream_urls.txt", "chip")
        self.btn_mon_save.clicked.connect(self.save_stream_urls)
        urow = QHBoxLayout()
        urow.setSpacing(12)
        urow.addWidget(self.btn_mon_autocopy)
        urow.addWidget(self.btn_mon_save)
        urow.addStretch()
        uv.addLayout(urow)
        v.addWidget(self.url_box)
        v.addStretch()
        scroll.setWidget(w)
        return scroll

    # ------------------------------------------------------------------ 设置
    def _tab_settings(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(2, 2, 8, 2)
        v.setSpacing(22)

        card = QFrame()
        card.setObjectName("Card")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(28, 24, 28, 26)
        cv.setSpacing(18)
        cv.addWidget(self._h2("推流配置"))
        desc = QLabel("保存后即时生效；自定义后台地址、抖音 / B站地址、上游 DNS 都在这里维护。"
                      "配置文件兼容旧版 bat（编码自动处理）。")
        desc.setObjectName("Muted")
        desc.setWordWrap(True)
        cv.addWidget(desc)

        g = QGridLayout()
        g.setHorizontalSpacing(18)
        g.setVerticalSpacing(14)
        self.edits = {}
        rows = [
            ("网关IP", "网关 IP（留空 = 自动检测，推荐）", "一般留空；仅在直连 / 特殊网络时手动指定"),
            ("上游DNS", "上游 DNS（“自动”= 自动测速选最快）", "PS5 改 DNS 后断网时，可改成加速器 DNS，如 8.8.8.1"),
            ("自定义推流地址", "自定义 RTMP 后台完整推流地址", "整串粘贴，必须 rtmp:// 开头，不要拆分"),
            ("抖音推流地址", "抖音推流地址", "用不到就留空"),
            ("抖音推流码", "抖音推流码", "每次开播可能变化"),
            ("B站推流地址", "B站推流地址", "用不到就留空"),
            ("B站推流码", "B站推流码", "每次开播可能变化"),
        ]
        for i, (key, label, hint) in enumerate(rows):
            lab = QLabel(label)
            lab.setMinimumWidth(280)
            lab.setObjectName("Muted")
            ed = QLineEdit()
            ed.setPlaceholderText(hint)
            g.addWidget(lab, i, 0)
            g.addWidget(ed, i, 1)
            self.edits[key] = ed
        self.chk_reencode = ToggleSwitch("重编码（后台黑屏 / 拉不到流时勾选；默认直接转发更省 CPU）")
        g.addWidget(self.chk_reencode, len(rows), 0, 1, 2)
        g.setColumnStretch(1, 1)
        cv.addLayout(g)

        brow = QHBoxLayout()
        brow.setSpacing(12)
        self.btn_save = PillButton("保存配置", "primary")
        self.btn_save.clicked.connect(self._save_settings)
        self.btn_reload = PillButton("重新加载配置文件", "chip")
        self.btn_reload.clicked.connect(self._reload_settings)
        self.btn_open_cfg = PillButton("打开工具目录", "chip")
        self.btn_open_cfg.clicked.connect(self.open_folder)
        brow.addWidget(self.btn_save)
        brow.addWidget(self.btn_reload)
        brow.addWidget(self.btn_open_cfg)
        brow.addStretch()
        cv.addLayout(brow)

        self.lbl_cfg_path = QLabel("配置文件：" + core.CONFIG_PATH)
        self.lbl_cfg_path.setObjectName("Faint")
        self.lbl_cfg_path.setWordWrap(True)
        cv.addWidget(self.lbl_cfg_path)
        v.addWidget(card)
        v.addStretch()
        scroll.setWidget(w)
        return scroll

    # ------------------------------------------------------------------ 诊断
    def _tab_diagnostics(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(2, 2, 8, 2)
        v.setSpacing(22)

        top = QFrame()
        top.setObjectName("Card")
        tv = QVBoxLayout(top)
        tv.setContentsMargins(28, 24, 28, 24)
        tv.setSpacing(14)
        tv.addWidget(self._h2("一键前置体检"))
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel("按哪个目标校验推流配置："))
        self.cmb_diag_platform = QComboBox()
        self.cmb_diag_platform.setMinimumWidth(150)
        for key, (name, _, _) in PLATFORMS.items():
            self.cmb_diag_platform.addItem(name, key)
        self.btn_check = PillButton("开始体检（含上游 DNS 测速）", "primary")
        self.btn_check.clicked.connect(self.run_preflight)
        self.btn_fw = PillButton("添加防火墙规则", "chip")
        self.btn_fw.clicked.connect(self.add_firewall)
        self.btn_cleanup = PillButton("停止并清理防火墙", "chip")
        self.btn_cleanup.clicked.connect(self.cleanup)
        row.addWidget(self.cmb_diag_platform)
        row.addWidget(self.btn_check)
        row.addWidget(self.btn_fw)
        row.addWidget(self.btn_cleanup)
        row.addStretch()
        tv.addLayout(row)

        self.preflight_scroll = QScrollArea()
        self.preflight_scroll.setWidgetResizable(True)
        self.preflight_scroll.setFrameShape(QFrame.NoFrame)
        self.preflight_scroll.setMinimumHeight(250)
        self.preflight_container = QWidget()
        self.preflight_layout = QVBoxLayout(self.preflight_container)
        self.preflight_layout.setContentsMargins(0, 0, 8, 0)
        self.preflight_layout.setSpacing(10)
        ph = QLabel("点击【开始体检】，将检查管理员权限、程序文件、本机网络、端口占用、"
                    "上游 DNS 与推流配置。")
        ph.setObjectName("Faint")
        ph.setWordWrap(True)
        self.preflight_layout.addWidget(ph)
        self.preflight_layout.addStretch()
        self.preflight_scroll.setWidget(self.preflight_container)
        tv.addWidget(self.preflight_scroll)
        v.addWidget(top)

        tree_card = QFrame()
        tree_card.setObjectName("Card")
        tcv = QVBoxLayout(tree_card)
        tcv.setContentsMargins(28, 24, 28, 24)
        tcv.setSpacing(12)
        tcv.addWidget(self._h3("出问题对照排查（按设备归因）"))
        self.trouble = QTreeWidget()
        self.trouble.setHeaderLabels(["设备", "现象", "原因与解决"])
        self.trouble.setColumnWidth(0, 190)
        self.trouble.setColumnWidth(1, 300)
        self.trouble.setAlternatingRowColors(False)
        self.trouble.setRootIsDecorated(False)
        self._build_trouble_tree()
        tcv.addWidget(self.trouble)
        v.addWidget(tree_card)
        v.addStretch()
        scroll.setWidget(w)
        return scroll

    def _build_trouble_tree(self):
        data = [
            ("DNS服务 / 本机电脑", "一键启动后提示 53 端口无法绑定 / Cannot bind port 53",
             "53 被加速器（AK 等）的 DNS 代理或系统服务占用：先一键停止，以管理员重启；"
             "仍失败就在加速器里关闭“DNS 代理/DNS 劫持”。体检会直接列出占用进程。"),
            ("加速器 / 本机电脑", "PS5 改 DNS 后断网 / 连不上互联网",
             "上游 DNS 全不通：确认电脑能上网、加速器已连接（可换节点）；把设置里上游 DNS 改成 8.8.8.1 后重开。"),
            ("PS5主机", "开播后一直没有【劫持成功】",
             "首选 DNS 没填对/没保存，或 PS5 没真正开始 Twitch 直播，或没先测试互联网连接。"
             "首选 DNS 填界面顶部 IP，备选留空，IP/掩码/网关照抄加速器。"),
            ("PS5主机", "PS5 上 5 个空怎么填",
             "IP/子网掩码/默认网关照抄加速器；只有“首选 DNS”换成界面顶部电脑 IP，备选 DNS 留空；MTU/代理不动。"),
            ("网络·路由器", "PS5 与电脑无法互通",
             "确认两者连同一个家用路由器（局域网模式），不是插电脑、也不是不同网络；"
             "有线路由器请关闭 AP 隔离/客户端隔离。"),
            ("MediaMTX", "MediaMTX 没有 is ready / 监看黑屏",
             "说明第 3 关劫持没过，画面没到电脑，先解决劫持；再确认 1935 未被其他推流软件占用。"),
            ("PS5主机", "转推一直“还没收到 PS5 流”",
             "PS5 没开播，或没出现劫持成功；回到第 3 关；确认 MediaMTX 已运行。"),
            ("推流后台/平台", "ffmpeg 在跑但后台黑屏",
             "后台不支持直接转发：到设置勾选【重编码】保存，再重新转推。"),
            ("推流后台/平台", "ffmpeg 报连接重置 / 404",
             "推流地址或推流码错误/过期：重新从后台复制；抖音/B站推流码每次开播会变。"),
            ("本机电脑", "提示找不到 ffmpeg",
             "安装 ffmpeg 加入系统 PATH，或把 ffmpeg.exe 放到工具目录的 ffmpeg 文件夹内后重启程序。"),
            ("本机电脑", "换了加速器/换了 WiFi 后失效",
             "电脑 IP 可能变了：一键启动后以界面顶部新的 IP 为准，把 PS5 首选 DNS 改成新值。"),
        ]
        for dev, sym, fix in data:
            it = QTreeWidgetItem([dev, sym, fix])
            for c in range(3):
                it.setToolTip(c, fix)
            self.trouble.addTopLevelItem(it)

    # ------------------------------------------------------------------ 日志
    def _tab_logs(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(2, 2, 8, 2)
        v.setSpacing(18)

        top = QFrame()
        top.setObjectName("Card")
        tv = QVBoxLayout(top)
        tv.setContentsMargins(28, 22, 28, 22)
        tv.setSpacing(14)
        hrow = QHBoxLayout()
        hrow.setSpacing(12)
        hrow.addWidget(self._h2("实时日志"))
        hrow.addStretch()
        lab = QLabel("来源")
        lab.setObjectName("Muted")
        hrow.addWidget(lab)
        self.cmb_log_filter = QComboBox()
        self.cmb_log_filter.setMinimumWidth(120)
        for f in ["全部", "系统", "DNS", "MediaMTX", "转推"]:
            self.cmb_log_filter.addItem(f)
        self.cmb_log_filter.currentTextChanged.connect(self._on_log_filter)
        hrow.addWidget(self.cmb_log_filter)
        self.chk_autoscroll = ToggleSwitch("自动滚动")
        self.chk_autoscroll.setChecked(True)
        hrow.addWidget(self.chk_autoscroll)
        btn_clear = PillButton("清空", "chip")
        btn_clear.clicked.connect(lambda: self.log_view.clear())
        btn_save = PillButton("导出日志", "chip")
        btn_save.clicked.connect(self._export_log)
        hrow.addWidget(btn_clear)
        hrow.addWidget(btn_save)
        tv.addLayout(hrow)
        v.addWidget(top)

        self.log_view = LogConsole()
        self.log_view.setPlaceholderText("暂无日志。程序启动、服务启停与转推状态都会实时记录在这里。")
        v.addWidget(self.log_view, 1)
        return w

    def _h2(self, text):
        l = QLabel(text)
        l.setObjectName("H2")
        return l

    def _h3(self, text):
        l = QLabel(text)
        l.setObjectName("H3")
        return l

    # ------------------------------------------------------------------ 托盘
    def _build_tray(self):
        icon_path = core.resource_path("assets", "app.ico")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else self.style().standardIcon(0)
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("PS5 直播推流助手")
        menu = QMenu()
        act_show = QAction("显示主界面", self)
        act_show.triggered.connect(self._restore)
        act_start = QAction("一键启动", self)
        act_start.triggered.connect(self.start_all)
        act_stop = QAction("一键停止", self)
        act_stop.triggered.connect(self.stop_all)
        act_quit = QAction("退出程序", self)
        act_quit.triggered.connect(self._quit_app)
        menu.addAction(act_show)
        menu.addAction(act_start)
        menu.addAction(act_stop)
        menu.addSeparator()
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: self._restore() if r == QSystemTrayIcon.DoubleClick else None)
        self.tray.show()

    def _restore(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # ------------------------------------------------------------------ 信号
    def _wire_signals(self):
        self.dns.log.connect(self.log)
        self.dns.mode_detected.connect(self._on_dns_mode)
        self.dns.upstream_tested.connect(self._on_upstream)
        self.dns.listening.connect(self._on_dns_listening)
        self.dns.hijacked.connect(self._on_hijack)
        self.dns.fatal.connect(self._on_dns_fatal)
        self.dns.stopped.connect(lambda: self.log("info", "系统", "DNS 服务已停止。"))

        self.mtx.log.connect(self.log)
        self.mtx.rtmp_ready.connect(self._on_rtmp_ready)
        self.mtx.path_ready.connect(self._on_path_ready)
        self.mtx.port_error.connect(self._on_mtx_port_error)
        self.mtx.failed.connect(self._on_proc_failed)
        self.mtx.exited_ok.connect(self._on_mtx_exited)

        self.relay.log.connect(self.log)
        self.relay.stage.connect(self._on_relay_stage)
        self.relay.stats.connect(self._on_relay_stats)
        self.relay.error.connect(self._on_relay_error)
        self.relay.finished.connect(lambda code: None)

    def log(self, level, source, msg):
        if hasattr(self, "log_view"):
            self.log_view.append(level, source, msg)
        if level == "error":
            self.tray.showMessage("PS5 直播推流助手", elide(msg, 80),
                                  QSystemTrayIcon.Warning, 4000)

    # ------------------------------------------------------------------ 设置
    def _load_settings(self):
        cfg = self.cfg
        self.edits["网关IP"].setText(cfg.get("网关IP", ""))
        self.edits["上游DNS"].setText(cfg.get("上游DNS", "") if cfg.get("上游DNS", "") else "自动")
        self.edits["自定义推流地址"].setText(cfg.get("自定义推流地址", ""))
        self.edits["抖音推流地址"].setText(cfg.get("抖音推流地址", ""))
        self.edits["抖音推流码"].setText(cfg.get("抖音推流码", ""))
        self.edits["B站推流地址"].setText(cfg.get("B站推流地址", ""))
        self.edits["B站推流码"].setText(cfg.get("B站推流码", ""))
        self.chk_reencode.setChecked(cfg.get("重编码", "否").strip() in ("是", "yes", "y", "1", "true"))
        self._on_platform_changed()

    def _save_settings(self):
        for key, ed in self.edits.items():
            self.cfg[key] = ed.text().strip()
        self.cfg["重编码"] = "是" if self.chk_reencode.isChecked() else "否"
        try:
            path = core.save_config(self.cfg)
            self.log("ok", "系统", "配置已保存：%s" % path)
            self.toast.show_msg("配置已保存", "ok")
        except Exception as e:
            self.toast.show_msg("配置保存失败：%s" % e, "error")

    def _reload_settings(self):
        self.cfg = core.load_config()
        self._load_settings()
        self.toast.show_msg("已重新加载配置文件", "info")

    def _on_platform_changed(self):
        if hasattr(self, "cmb_diag_platform"):
            self.cmb_diag_platform.setCurrentIndex(self.cmb_platform.currentIndex())

    # ------------------------------------------------------------------ IP
    def _on_ip_detected(self, res):
        if isinstance(res, dict):
            return
        ip, mode = res
        self.current_ip, self.current_mode = ip or "", mode
        if ip:
            self.lbl_ip.setText(ip)
            self.log("info", "系统", "检测到本机局域网 IP：%s（%s），PS5 首选 DNS 填它。"
                     % (ip, {"direct": "直连", "router": "局域网", "manual": "手动"}.get(mode, mode)))
        else:
            self.lbl_ip.setText("未检测到")
            self.log("warn", "系统", "未检测到可用局域网 IP，请确认电脑已联网。")

    def _copy_ip(self):
        if self.current_ip:
            QApplication.clipboard().setText(self.current_ip)
            self.toast.show_msg("已复制首选 DNS：%s" % self.current_ip, "ok")
        else:
            self.toast.show_msg("还没检测到 IP，请先联网", "error")

    # ------------------------------------------------------------------ 启停
    def _ensure_admin(self):
        if core.is_admin():
            return True
        if getattr(sys, "frozen", False):
            self.toast.show_msg("需要管理员权限，正在重新申请…", "warn")
            try:
                ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", sys.executable, "", None, 1)
            except Exception:
                pass
            QApplication.quit()
        else:
            QMessageBox.warning(self, "需要管理员权限",
                "绑定 DNS 53 端口和添加防火墙规则需要管理员权限。\n"
                "请右键“以管理员身份运行”，或通过打包后的 EXE 启动（会自动弹 UAC）。")
        return False

    def start_all(self):
        if self.dns.is_running() or (self.mtx.is_running()):
            self.toast.show_msg("服务已在运行中", "info")
            return
        if not self._ensure_admin():
            return
        self._stopping = False
        self.state.reset()
        self.state.started = True
        self.state.started_ts = time.time()
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.hero_status.setText("启动中")
        self.hero_status.setStyleSheet("color:%s;" % COLORS["accent"])
        self.hero_sub.setText("正在添加防火墙、启动 MediaMTX 与 DNS 劫持…")
        self.log("info", "系统", "========== 一键启动 ==========")

        self.add_firewall(silent=True)
        self.mtx.start_mtx()
        self.dns.start(self.cfg.get("网关IP", ""), self.cfg.get("上游DNS", "自动") or "自动")
        self.refresh_gates()

    def stop_all(self):
        self._stopping = True
        self.log("info", "系统", "========== 一键停止 ==========")
        self.relay.stop()
        self.mtx.stop()
        self.dns.stop()
        self.state.reset()
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.hero_status.setText("已停止")
        self.hero_status.setStyleSheet("color:%s;" % COLORS["text"])
        self.hero_sub.setText("所有服务已停止。再次开播点【一键启动】。")
        self.pill_mtx.set_state("stop", "未运行")
        self.pill_dns.set_state("stop", "未运行")
        self.pill_fw.set_state("stop", "未添加规则")
        self.pill_relay_reset()
        self.toast.show_msg("已停止全部服务", "ok")
        self.refresh_gates()

    def cleanup(self):
        self.stop_all()
        self.log("info", "系统", "正在删除防火墙规则…")
        self.toast.show_msg("正在清理防火墙规则…", "info")

        def job():
            return core.remove_firewall_rules()
        t = TaskThread(job)
        self._fw_thread = t
        t.result.connect(self._on_firewall_removed)
        t.start()

    def add_firewall(self, silent=False):
        def job():
            return core.add_firewall_rules()
        t = TaskThread(job)
        self._fw_thread = t
        t.result.connect(lambda r: self._on_firewall_added(r, silent))
        t.start()
        if not silent:
            self.toast.show_msg("正在添加防火墙规则…", "info")

    def _on_firewall_added(self, res, silent):
        if isinstance(res, dict):
            self.state.firewall_ok = False
            self.toast.show_msg("防火墙规则添加失败：" + res.get("__error__", ""), "error")
            return
        ok_all = all(r[3] for r in res)
        self.state.firewall_ok = ok_all
        self.state.firewall_done = True
        for name, proto, port, ok, out in res:
            if ok:
                self.log("ok", "系统", "防火墙放行 %s %s 端口 %d" % (name, proto, port))
            else:
                self.log("error", "系统", "防火墙规则 %s(%s/%d) 添加失败：%s" % (name, proto, port, out))
        if not silent:
            self.toast.show_msg("防火墙规则已添加" if ok_all else "部分防火墙规则失败，见日志",
                                "ok" if ok_all else "error")
        self.refresh_gates()

    def _on_firewall_removed(self, res):
        if isinstance(res, dict):
            self.toast.show_msg("清理失败：" + res.get("__error__", ""), "error")
            return
        self.state.firewall_ok = False
        self.state.firewall_done = True
        self.pill_fw.set_state("stop", "未添加规则")
        self.log("ok", "系统", "防火墙规则已删除，系统改动已撤回。")
        self.toast.show_msg("已清理：进程停止、防火墙规则删除", "ok")

    # ------------------------------------------------------------------ DNS 回调
    def _on_dns_mode(self, mode, ip):
        self.current_ip, self.current_mode = ip, mode
        self.lbl_ip.setText(ip)

    def _on_upstream(self, ip, ok, ms, desc):
        self.state.upstream_total += 1
        if ok:
            self.state.upstream_usable += 1

    def _on_dns_listening(self, ip):
        self.state.dns_listening = True
        self.state.dns_listening_ts = time.time()
        self.state.dns_fatal = None

    def _on_hijack(self, domain, ip):
        self.state.hijack_count += 1
        self.state.last_hijack = domain
        self.state.last_hijack_ts = time.time()

    def _on_dns_fatal(self, code, detail):
        self.state.dns_fatal = (code, detail)
        self.log("error", "系统", "DNS 致命错误：%s" % detail.replace("\n", " "))
        self.toast.show_msg("DNS 服务异常：%s" % detail.split("。")[0][:40], "error")

    # ------------------------------------------------------------------ MediaMTX
    def _on_rtmp_ready(self):
        self.state.mtx_1935 = True

    def _on_path_ready(self, name):
        self.state.stream_ready = True
        self.state.stream_path = name
        self.state.stream_ready_ts = time.time()
        self.toast.show_msg("已收到 PS5 画面：%s" % elide(name, 40), "ok")

    def _on_mtx_port_error(self, line):
        self.log("error", "MediaMTX", "端口绑定失败：" + line)
        self.toast.show_msg("MediaMTX 端口被占用，见诊断页", "error")

    def _on_proc_failed(self, source, msg):
        self.log("error", source, msg)
        self.toast.show_msg("%s 启动失败：%s" % (source, msg[:40]), "error")

    def _on_mtx_exited(self, source, code):
        if not self._stopping:
            self.state.mtx_1935 = False
            self.log("error", "MediaMTX", "MediaMTX 已退出（退出码 %s），可能被杀毒拦截或端口被抢。" % code)

    # ------------------------------------------------------------------ 转推
    def _on_relay_clicked(self):
        if self.relay.is_active() or self.relay.is_waiting():
            self.relay.stop()
            return
        self._save_settings_silent()
        platform = self.cmb_platform.currentData()
        self.state.pushing_ts = time.time()
        self.relay.start_relay(self.cfg, platform,
                               self.state.stream_path if self.state.stream_ready else None)

    def _save_settings_silent(self):
        for key, ed in self.edits.items():
            self.cfg[key] = ed.text().strip()
        self.cfg["重编码"] = "是" if self.chk_reencode.isChecked() else "否"
        try:
            core.save_config(self.cfg)
        except Exception:
            pass

    def _on_relay_stage(self, st):
        self.state.relay_stage = st
        if st == "waiting":
            self.btn_relay.setText("停止等待")
            self.lbl_relay_stats.setText("正在等待 PS5 推流到达本机…")
        elif st == "pushing":
            self.btn_relay.setText("停止转推")
            self.lbl_relay_stats.setText("ffmpeg 启动中，等待画面帧…")
        elif st == "done":
            self.btn_relay.setText("开始转推")
            self.lbl_relay_stats.setText("转推已结束")
        elif st == "error":
            self.btn_relay.setText("开始转推")
        elif st == "idle":
            self.btn_relay.setText("开始转推")
            self.lbl_relay_stats.setText("未开始转推")
            self.state.relay_frame_moving = False

    def _on_relay_stats(self, s):
        self.state.relay_frame = int(s.get("frame", -1))
        self.state.relay_stage = "pushing"
        self.lbl_relay_stats.setText(
            "正在转推 · 帧 %s · fps %s · 码率 %s · 时间 %s"
            % (s.get("frame"), s.get("fps"), s.get("bitrate"), s.get("time")))

    def _on_relay_error(self, device, msg):
        self.state.relay_error = msg
        self.state.relay_stage = "error"
        self.log("error", "转推", "【%s】%s" % (device, msg))
        self.toast.show_msg("【%s】%s" % (device, msg.split("：")[0][:40]), "error")
        self.refresh_gates()

    def pill_relay_reset(self):
        self.btn_relay.setText("开始转推")
        self.lbl_relay_stats.setText("未开始转推")
        self.state.relay_stage = "idle"
        self.state.relay_error = None

    # ------------------------------------------------------------------ 监看
    def _current_urls(self):
        path = self.state.stream_path
        if not path:
            return None
        return build_watch_urls(path)

    def _require_stream(self, action):
        if not self.state.stream_ready:
            self.toast.show_msg("还没收到 PS5 画面，请先一键启动并在 PS5 开始直播", "warn")
            return False
        return True

    def watch_webrtc(self):
        if not self._require_stream("webrtc"):
            return
        urls = self._current_urls()
        core.open_url(urls["webrtc_page"])
        self.log("info", "系统", "已打开 WebRTC 监看页：" + urls["webrtc_page"])

    def watch_hls(self):
        if not self._require_stream("hls"):
            return
        urls = self._current_urls()
        core.open_url(urls["hls_page"])
        self.log("info", "系统", "已打开 HLS 监看页：" + urls["hls_page"])

    def copy_rtmp(self):
        if not self._require_stream("rtmp"):
            return
        urls = self._current_urls()
        QApplication.clipboard().setText(urls["rtmp"])
        self.toast.show_msg("已复制 RTMP 拉流地址，到直播伴侣 Ctrl+V", "ok")

    def copy_hls(self):
        if not self._require_stream("hls"):
            return
        urls = self._current_urls()
        QApplication.clipboard().setText(urls["hls"])
        self.toast.show_msg("已复制 HLS 拉流地址", "ok")

    def _copy_url(self, key):
        urls = self._current_urls()
        if not urls:
            self.toast.show_msg("还没有在线流地址", "warn")
            return
        QApplication.clipboard().setText(urls[key])
        self.toast.show_msg("已复制", "ok")

    def save_stream_urls(self):
        urls = self._current_urls()
        if not urls:
            self.toast.show_msg("还没有在线流，无法保存", "warn")
            return
        try:
            with open(core.STREAM_URLS_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join([
                    "PS5 stream pull URLs", "",
                    "RTMP : " + urls["rtmp"], "HLS  : " + urls["hls"], "",
                    "WebRTC page: " + urls["webrtc_page"],
                    "HLS page   : " + urls["hls_page"], "",
                ]))
            self.toast.show_msg("已保存 stream_urls.txt", "ok")
            self.log("ok", "系统", "拉流地址已保存：" + core.STREAM_URLS_FILE)
        except Exception as e:
            self.toast.show_msg("保存失败：%s" % e, "error")

    def open_folder(self):
        if core.open_in_explorer(core.BASE_DIR):
            return
        if os.path.exists(core.CONFIG_PATH):
            core.open_in_explorer(core.CONFIG_PATH)

    def refresh_monitor(self):
        items, err = fetch_paths()
        self.list_paths.clear()
        ready = [it for it in items if it.get("ready")]
        if not ready:
            it = QListWidgetItem("暂无在线流（请先一键启动，并在 PS5 开始 Twitch 直播）")
            it.setForeground(QColor(COLORS["faint"]))
            self.list_paths.addItem(it)
            for key, val in self.url_rows.items():
                val.clear()
            return
        for it in ready:
            name = it.get("name", "")
            row = QListWidgetItem(("● " if name.startswith("app/") else "    ") + name +
                                  ("        ← PS5 源" if name.startswith("app/") else ""))
            if name.startswith("app/"):
                row.setForeground(QColor(COLORS["ok"]))
            self.list_paths.addItem(row)
        path = pick_ps5_path(items)
        if path:
            self.state.stream_ready = True
            self.state.stream_path = path
            urls = build_watch_urls(path)
            for key, val in self.url_rows.items():
                val.setText(urls[key])

    # ------------------------------------------------------------------ 体检
    def run_preflight(self):
        self._save_settings_silent()
        platform = self.cmb_diag_platform.currentData()
        self._clear_preflight()
        lab = QLabel("正在体检（上游 DNS 测速约需数秒）…")
        lab.setStyleSheet("color:%s;" % COLORS["accent"])
        self.preflight_layout.insertWidget(0, lab)
        self.btn_check.setEnabled(False)
        t = TaskThread(run_preflight, self.cfg, platform, False)
        self._preflight_thread = t
        t.result.connect(self._on_preflight_done)
        t.start()

    def _clear_preflight(self):
        while self.preflight_layout.count():
            item = self.preflight_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _on_preflight_done(self, res):
        self.btn_check.setEnabled(True)
        self._clear_preflight()
        if isinstance(res, dict):
            lab = QLabel("体检失败：" + res.get("__error__", ""))
            lab.setStyleSheet("color:%s;" % COLORS["error"])
            lab.setWordWrap(True)
            self.preflight_layout.addWidget(lab)
            self.preflight_layout.addStretch()
            return
        worst = OK
        for r in res:
            if r.level == ERROR:
                worst = ERROR
            elif r.level == WARN and worst != ERROR:
                worst = WARN
            self.preflight_layout.addWidget(self._check_widget(r))
        self.preflight_layout.addStretch()
        tip = {OK: "全部检查通过，可以一键启动。",
               WARN: "存在警告项（不影响收流，但可能影响转推或稳定性）。",
               ERROR: "存在必须处理的错误，按建议修复后再启动。"}[worst]
        self.toast.show_msg(tip, "ok" if worst == OK else ("warn" if worst == WARN else "error"))

    def _check_widget(self, r):
        f = QFrame()
        f.setObjectName("PanelCard")
        col = {"ok": COLORS["ok"], "warn": COLORS["warn"], "error": COLORS["error"]}[r.level]
        v = QVBoxLayout(f)
        v.setContentsMargins(18, 14, 18, 14)
        v.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(10)
        dot = QFrame()
        dot.setFixedSize(9, 9)
        dot.setStyleSheet("background:%s;border:none;border-radius:4px;" % col)
        title = QLabel(r.title)
        title.setStyleSheet("font-weight:600;")
        chip = DeviceChip(r.device, DEVICES.get(r.device, r.device))
        top.addWidget(dot)
        top.addWidget(title, 1)
        top.addWidget(chip)
        v.addLayout(top)
        detail = QLabel(r.detail)
        detail.setWordWrap(True)
        detail.setStyleSheet("color:%s;" % COLORS["text"])
        v.addWidget(detail)
        if r.suggestion:
            sug = QLabel("→  " + r.suggestion)
            sug.setWordWrap(True)
            sug.setStyleSheet("color:%s;" % COLORS["accent"])
            v.addWidget(sug)
        return f

    # ------------------------------------------------------------------ 5 关
    def _on_gate_click(self, gate_id):
        self.set_page(3)
        help_info = GATE_HELP.get(gate_id)
        dev_names = set()
        if help_info:
            for dev, _sym, _fix in help_info["tips"]:
                dev_names.add(DEVICES.get(dev, dev))
        for i in range(self.trouble.topLevelItemCount()):
            it = self.trouble.topLevelItem(i)
            col = it.text(0)
            if any(name.split("/")[0] in col or name in col for name in dev_names):
                self.trouble.setCurrentItem(it)
                self.trouble.scrollToItem(it)
                break
        self.toast.show_msg("已打开诊断页，底部为该关卡排障方法", "info")

    def refresh_gates(self):
        gates, diagnosis = evaluate(self.state)
        for card, g in zip(self.gate_cards, gates):
            card.set_state(g["status"], g["detail"])
        self._update_hero(gates)
        self._update_pills()
        self._update_diagnosis(diagnosis)

    def _update_hero(self, gates):
        if not self.state.started:
            self.hero_status.setText("未启动")
            self.hero_status.setStyleSheet("color:%s;" % COLORS["text"])
            self.hero_sub.setText("点击【一键启动】，开启收流与 DNS 劫持；PS5 首选 DNS 填下方地址")
            return
        if self.state.dns_fatal:
            self.hero_status.setText("服务异常")
            self.hero_status.setStyleSheet("color:%s;" % COLORS["error"])
            self.hero_sub.setText("有错误需要处理，见下方诊断卡（已标注设备与原因）")
            return
        statuses = [g["status"] for g in gates]
        if statuses[0] == "ok":
            if statuses[2] == "ok":
                self.hero_status.setText("运行中 · 已劫持 %d 次" % self.state.hijack_count)
                self.hero_status.setStyleSheet("color:%s;" % COLORS["ok"])
                self.hero_sub.setText("PS5 推流已引到电脑。去监看看画面，或直接开始转推。")
            else:
                self.hero_status.setText("运行中 · 等待 PS5 开播")
                self.hero_status.setStyleSheet("color:%s;" % COLORS["accent"])
                self.hero_sub.setText("在 PS5 上：创建键 → 直播 → Twitch → 开始直播，第 3 关会变绿")
        else:
            self.hero_status.setText("启动中")
            self.hero_status.setStyleSheet("color:%s;" % COLORS["accent"])
            self.hero_sub.setText("正在启动 MediaMTX 与 DNS 服务…")

    def _update_pills(self):
        if self.mtx.is_running():
            if self.state.mtx_1935:
                self.pill_mtx.set_state("run", "1935 监听中")
            else:
                self.pill_mtx.set_state("busy", "启动中")
        else:
            self.pill_mtx.set_state("stop", "未运行")
        if self.state.dns_fatal:
            self.pill_dns.set_state("error", "异常")
        elif self.state.dns_listening:
            self.pill_dns.set_state("run", "53 监听中")
        elif self.dns.is_running():
            self.pill_dns.set_state("busy", "测速/绑定中")
        else:
            self.pill_dns.set_state("stop", "未运行")
        if self.state.firewall_ok:
            self.pill_fw.set_state("run", "53/1935 已放行")
        elif self.state.started and not self.state.firewall_done:
            self.pill_fw.set_state("busy", "配置中")
        elif self.state.started and self.state.firewall_done:
            self.pill_fw.set_state("error", "添加失败（需管理员）")
        else:
            self.pill_fw.set_state("stop", "未添加规则")

    def _update_diagnosis(self, diagnosis):
        if not diagnosis:
            self.diag.hide()
            return
        gate_id, kind, device, title, detail = diagnosis
        self.diag.show()
        border = COLORS["error"] if kind == "error" else COLORS["warn"]
        self.diag.setStyleSheet(
            "QFrame#PanelCard{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 %s,stop:1 %s);border:1px solid %s;border-radius:%dpx;}"
            % (COLORS["panel_top"], COLORS["panel_bot"], border, R_CARD))
        self.diag_chip.set_device(device, DEVICES.get(device, device))
        kind_txt = "出现问题" if kind == "error" else "等待较久，重点排查"
        self.diag_title.setText("【%s】%s · %s" % (DEVICES.get(device, device), title, kind_txt))
        self.diag_title.setStyleSheet("font-weight:600;color:%s;" % border)
        self.diag_body.setText(detail)
        help_info = GATE_HELP.get(gate_id)
        if help_info:
            lines = ["<br>按可能性排序："]
            for i, (dev, sym, fix) in enumerate(help_info["tips"], 1):
                lines.append("<b>%d.［%s］%s</b>　%s" % (i, DEVICES.get(dev, dev), sym, fix))
            self.diag_tips.setText("<br>".join(lines))
        else:
            self.diag_tips.setText("")

    # ------------------------------------------------------------------ 定时
    def _tick(self):
        if self.state.started and self.mtx.is_running():
            items, err = fetch_paths(timeout=1)
            if items:
                path = pick_ps5_path(items)
                if path and path != self.state.stream_path:
                    self.state.stream_ready = True
                    self.state.stream_path = path
                    self.state.stream_ready_ts = time.time()
        if self.current_page() == 1 and self.mtx.is_running():
            self.refresh_monitor()
        if self.state.relay_stage == "pushing":
            cur = self.state.relay_frame
            if cur >= 0 and cur > self._prev_frame:
                self.state.relay_frame_moving = True
            self._prev_frame = cur
        if self.state.started and not self.dns.is_running() and not self.state.dns_listening \
                and not self.state.dns_fatal and not self._stopping:
            if time.time() - self.state.started_ts > 8:
                self.state.dns_fatal = ("unknown", "DNS 服务未能启动，请查看日志页并以管理员身份重试。")
        self.refresh_gates()

    # ------------------------------------------------------------------ 日志筛选/导出
    def _on_log_filter(self, text):
        self.log_view.set_filter(text)

    def _export_log(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出日志", os.path.join(core.BASE_DIR, "ps5live_log.txt"),
                                              "文本文件 (*.txt)")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.log_view.toPlainText())
                self.toast.show_msg("日志已导出", "ok")
            except Exception as e:
                self.toast.show_msg("导出失败：%s" % e, "error")

    # ------------------------------------------------------------------ 关闭
    def _on_close(self):
        if self.dns.is_running() or self.mtx.is_running() or self.relay.is_active():
            box = QMessageBox(self)
            box.setWindowTitle("服务仍在运行")
            box.setText("收流/转推服务还在运行。要怎么处理？")
            b_min = box.addButton("最小化到托盘", QMessageBox.AcceptRole)
            b_stop = box.addButton("停止服务并退出", QMessageBox.DestructiveRole)
            b_cancel = box.addButton("取消", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() == b_min:
                self.hide()
                self.tray.showMessage("PS5 直播推流助手", "程序最小化到托盘，继续运行中。",
                                      QSystemTrayIcon.Information, 2500)
            elif box.clickedButton() == b_stop:
                self._quit_app()
        else:
            self._quit_app()

    def _quit_app(self):
        try:
            self.relay.stop()
            self.mtx.hard_stop()
            self.dns.stop()
        except Exception:
            pass
        self.tray.hide()
        QApplication.quit()
