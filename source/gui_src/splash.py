# -*- coding: utf-8 -*-
"""启动动画（极简版）：纯白玻璃卡片 + 蓝色标记 + 细进度条，克制淡入淡出。"""
import math

from PySide6.QtCore import Qt, QTimer, QVariantAnimation, QPointF, QRectF, QPropertyAnimation
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QPainterPath, QFont,
                           QLinearGradient, QRadialGradient)
from PySide6.QtWidgets import QWidget, QGraphicsOpacityEffect

from theme import COLORS
from widgets import ProgressBar


class Splash(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.SplashScreen |
                            Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(560, 348)

        self._angle = 0.0
        self._wave = 0.0
        self._opacity = 0.0
        self._done = False

        # 旋转细环
        self.rot = QVariantAnimation(self)
        self.rot.setStartValue(0.0)
        self.rot.setEndValue(360.0)
        self.rot.setDuration(2400)
        self.rot.setLoopCount(-1)
        self.rot.valueChanged.connect(self._on_rot)
        # 波纹
        self.wave = QVariantAnimation(self)
        self.wave.setStartValue(0.0)
        self.wave.setEndValue(1.0)
        self.wave.setDuration(2000)
        self.wave.setLoopCount(-1)
        self.wave.valueChanged.connect(self.update)

        self.eff = QGraphicsOpacityEffect(self)
        self.eff.setOpacity(0.0)
        self.setGraphicsEffect(self.eff)
        self.fade = QPropertyAnimation(self.eff, b"opacity", self)
        self.fade.setDuration(420)

        self.status_text = "正在初始化…"
        self.progress = 0.0
        self._cb = None

        # 拖动 / 点击跳过
        self.skip_callback = None
        self._drag_offset = None
        self._press_pos = None
        self._drag_moved = False
        self.setCursor(Qt.PointingHandCursor)

        self.bar = ProgressBar(self, 4)
        self.bar.setGeometry(70, 278, 420, 4)

    # ---------- 可拖动 / 点击跳过 ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            g = e.globalPosition().toPoint()
            self._press_pos = g
            self._drag_offset = g - self.frameGeometry().topLeft()
            self._drag_moved = False
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag_offset is not None and (e.buttons() & Qt.LeftButton):
            g = e.globalPosition().toPoint()
            if (g - self._press_pos).manhattanLength() > 5:
                self._drag_moved = True
                self.move(g - self._drag_offset)
            e.accept()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            if not self._drag_moved and self.skip_callback:
                self.skip_callback()
            self._drag_offset = None
            self._press_pos = None
            e.accept()

    # ---------- 显示/隐藏 ----------
    def start(self):
        self.center()
        self.show()
        self.rot.start()
        self.wave.start()
        self.fade.stop()
        self.fade.setStartValue(0.0)
        self.fade.setEndValue(1.0)
        self.fade.start()

    def center(self):
        from PySide6.QtWidgets import QApplication
        geo = QApplication.primaryScreen().availableGeometry()
        self.move(geo.center().x() - self.width() // 2,
                  geo.center().y() - self.height() // 2)

    def set_status(self, text, progress=None):
        self.status_text = text
        if progress is not None:
            self.progress = progress
            self.bar.set_value(progress, animate=True)
        self.update()

    def set_progress(self, v):
        self.progress = v
        self.bar.set_value(v)
        self.update()

    def finish(self, cb=None):
        if self._done:
            return
        self._done = True
        self._cb = cb
        self.fade.stop()
        self.fade.setStartValue(self.eff.opacity())
        self.fade.setEndValue(0.0)
        self.fade.finished.connect(self._after_fade)
        self.fade.start()

    def _after_fade(self):
        self.rot.stop()
        self.wave.stop()
        self.close()
        if self._cb:
            self._cb()

    def _on_rot(self, v):
        self._angle = float(v)
        self.update()

    # ---------- 绘制 ----------
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(1.5, 1.5, self.width() - 3, self.height() - 3)
        radius = 22

        # 纯白玻璃卡片
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        p.fillPath(path, QBrush(QColor(COLORS["bg"])))
        p.setPen(QPen(QColor(COLORS["border"]), 1))
        p.drawPath(path)

        accent = QColor(COLORS["accent"])
        text_col = QColor(COLORS["text"])
        muted = QColor(COLORS["muted"])
        faint = QColor(COLORS["faint"])

        # ---- 中央标记：蓝色圆角方块 + 白色播放三角 + cast 波纹 ----
        cx, cy = self.width() / 2, 118
        tile_w, tile_h = 62.0, 44.0
        tile = QRectF(cx - tile_w / 2, cy - tile_h / 2, tile_w, tile_h)

        # 细旋转环（进度感，克制）
        for k in range(3):
            a0 = self._angle + k * 120
            seg = QRectF(cx - 52, cy - 52, 104, 104)
            alpha = 150 - k * 42
            pen = QPen(QColor(accent.red(), accent.green(), accent.blue(), max(alpha, 20)))
            pen.setWidthF(1.6)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawArc(seg, int(-a0 * 16), int(56 * 16))

        # 波纹（隐去，保持极简：只在方块外围极淡一圈）
        v = self.wave.currentValue()
        rr = 46 + v * 12
        p.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(),
                             int(46 * (1 - v))), 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(cx - rr, cy - rr * 0.70, rr * 2, rr * 1.40),
                          rr * 0.30, rr * 0.30)

        # 蓝色方块
        g = QLinearGradient(tile.topLeft(), tile.bottomRight())
        g.setColorAt(0, QColor(COLORS["accent_hover"]))
        g.setColorAt(1, QColor(COLORS["accent"]))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawRoundedRect(tile, 12, 12)

        # 白色播放三角
        p.setBrush(QColor("white"))
        tri = QPainterPath()
        tri.moveTo(cx - 9, cy - 12)
        tri.lineTo(cx - 9, cy + 12)
        tri.lineTo(cx + 13, cy)
        tri.closeSubpath()
        p.drawPath(tri)

        # ---- 标题 ----
        f = QFont()
        f.setFamilies(["Segoe UI Variable Display", "Segoe UI",
                       "Microsoft YaHei UI", "Microsoft YaHei"])
        f.setPixelSize(23)
        f.setBold(True)
        f.setLetterSpacing(QFont.AbsoluteSpacing, -0.4)
        p.setFont(f)
        p.setPen(text_col)
        p.drawText(QRectF(0, 178, self.width(), 34), Qt.AlignHCenter,
                   "PS5 直播推流助手")

        f2 = QFont()
        f2.setFamilies(["Segoe UI", "Microsoft YaHei UI"])
        f2.setPixelSize(13)
        p.setFont(f2)
        p.setPen(muted)
        p.drawText(QRectF(0, 214, self.width(), 22), Qt.AlignHCenter,
                   "无采集卡 · 无 Remote Play · 一键收流转推")

        # ---- 状态文字 ----
        f3 = QFont()
        f3.setFamilies(["Segoe UI", "Microsoft YaHei UI"])
        f3.setPixelSize(12)
        p.setFont(f3)
        p.setPen(accent)
        p.drawText(QRectF(70, 292, self.width() - 140, 22),
                   Qt.AlignLeft | Qt.AlignVCenter, self.status_text)
        p.setPen(faint)
        p.drawText(QRectF(70, 292, self.width() - 140, 22),
                   Qt.AlignRight | Qt.AlignVCenter,
                   "%d%%" % int(self.progress * 100))

        f4 = QFont()
        f4.setFamilies(["Segoe UI", "Microsoft YaHei UI"])
        f4.setPixelSize(11)
        p.setFont(f4)
        p.setPen(QColor(faint.red(), faint.green(), faint.blue(), 170))
        p.drawText(QRectF(0, 320, self.width(), 18), Qt.AlignHCenter,
                   "可拖动 · 点击任意处进入")
        p.end()
