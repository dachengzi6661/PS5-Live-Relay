# -*- coding: utf-8 -*-
"""自定义控件（玻璃质感版）。

设计语言：极简、克制、留白充足。
- 窗口按钮：矢量自绘，悬停为浅灰圆角方块（关闭键保留系统惯例的柔和红）。
- 状态图标：细描边圆形 + 克制的脉冲；成功/失败用 系统绿/红填充。
- 关卡卡片：纯玻璃卡 + 发丝描边，状态只通过图标与描边色轻提示。
- 设备标签：统一灰阶（不引入第二品牌色），仅用深浅区分。
"""
from datetime import datetime

from PySide6.QtCore import (Qt, Signal, QThread, QVariantAnimation,
                            QPointF, QRectF)
from PySide6.QtGui import (QPainter, QColor, QFont, QPen, QBrush, QPainterPath,
                           QLinearGradient)
from PySide6.QtWidgets import (QWidget, QLabel, QFrame, QPlainTextEdit, QHBoxLayout,
                               QVBoxLayout, QPushButton, QCheckBox)

from theme import COLORS, DEVICE_COLORS, level_color, R_CARD
from diagnostics import DEVICES

STATE_COLORS = {
    "pending": COLORS["pending"],
    "active": COLORS["accent"],
    "ok": COLORS["ok"],
    "fail": COLORS["error"],
}


def _c(hexs, alpha=255):
    c = QColor(hexs)
    c.setAlpha(alpha)
    return c


def tracking(label, px):
    """QSS 不支持 letter-spacing，用 QFont 精确设置字距（大标题为负字距）。"""
    f = label.font()
    f.setLetterSpacing(QFont.AbsoluteSpacing, px)
    label.setFont(f)
    return label


class PillButton(QPushButton):
    """胶囊按钮（自绘）。

    为什么自绘：Qt 在「父控件带样式表 / 无边框透明窗」等组合下，QSS 对
    QPushButton 的 background / border-radius 偶发失效，胶囊会退化成直角方块。
    自绘保证任何环境下都是连续曲率胶囊 + 玻璃质感高光。

    kind:
      primary —— 品牌蓝实心胶囊（白字）
      ghost   —— 中性玻璃胶囊（发丝描边，悬停淡灰填充）
      chip    —— 更紧凑的中性玻璃胶囊
    """

    SPEC = {
        "primary": dict(pad=34, fs=15, h=46, weight=QFont.DemiBold),
        "ghost":   dict(pad=34, fs=15, h=46, weight=QFont.DemiBold),
        "chip":    dict(pad=18, fs=13, h=36, weight=QFont.Medium),
    }

    def __init__(self, text="", kind="ghost", parent=None):
        super().__init__(text, parent)
        self.kind = kind
        sp = self.SPEC.get(kind, self.SPEC["chip"])
        self._pad = sp["pad"]
        self.setMinimumHeight(sp["h"])
        f = self.font()
        f.setPixelSize(sp["fs"])
        f.setWeight(sp["weight"])
        f.setFamilies(["Segoe UI Variable Text", "Segoe UI Variable Display",
                       "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei"])
        self.setFont(f)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover, True)
        # 关掉原生绘制，背景完全自绘
        self.setStyleSheet("background:transparent;border:none;padding:0px;")
        self._hover = False
        self._down = False

    # ---- 尺寸 ----
    def sizeHint(self):
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(self.font())
        w = fm.horizontalAdvance(self.text()) + self._pad * 2
        return QSize(max(w, 72), self.minimumHeight())

    def minimumSizeHint(self):
        return self.sizeHint()

    # ---- 状态 ----
    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self._down = False
        self.update()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        self._down = True
        self.update()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        self._down = False
        self.update()
        super().mouseReleaseEvent(e)

    # ---- 绘制 ----
    def paintEvent(self, e):
        c = COLORS
        dark = c.get("mode") == "dark"
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        radius = r.height() / 2.0
        enabled = self.isEnabled()

        if self.kind == "primary":
            if not enabled:
                fill = QColor(0, 0, 0, 20) if not dark else QColor(255, 255, 255, 20)
                fg = QColor(c["dis_fg"])
                edge = QColor(0, 0, 0, 0)
            else:
                base = c["accent"]
                if self._down:
                    base = c["accent_press"]
                elif self._hover:
                    base = c["accent_hover"]
                fill = QColor(base)
                fg = QColor("white")
                edge = QColor(0, 0, 0, 0)
        else:
            if not enabled:
                fill = QColor(0, 0, 0, 0)
                fg = QColor(c["dis_fg"])
                edge = QColor(0, 0, 0, 18) if not dark else QColor(255, 255, 255, 22)
            else:
                if self._down:
                    fill = _c("#000000", 30) if not dark else _c("#ffffff", 18)
                elif self._hover:
                    fill = _c("#000000", 16) if not dark else _c("#ffffff", 30)
                else:
                    fill = QColor(0, 0, 0, 0)
                fg = QColor(c["text"])
                edge = QColor(c["btn_ghost_edge"])

        # 液滴投影（仅主按钮，极淡）
        if self.kind == "primary" and enabled:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 113, 227, 26 if not dark else 60))
            p.drawRoundedRect(r.adjusted(0, 2.5, 0, 2.5), radius, radius)

        p.setPen(QPen(edge, 1) if edge.alpha() else Qt.NoPen)
        p.setBrush(QBrush(fill))
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        p.setPen(fg)
        p.setFont(self.font())
        p.drawText(self.rect(), Qt.AlignCenter, self.text())
        p.end()


class SegButton(QPushButton):
    """分段控件按钮（自绘）：选中态为白色胶囊，未选中为透明，悬停淡灰。"""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover, True)
        self.setFixedHeight(30)
        self.setStyleSheet("background:transparent;border:none;padding:0px;")
        f = self.font()
        f.setPixelSize(13)
        f.setWeight(QFont.Medium)
        f.setFamilies(["Segoe UI Variable Text", "Segoe UI",
                       "Microsoft YaHei UI", "Microsoft YaHei"])
        self.setFont(f)
        self._hover = False

    def sizeHint(self):
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(self.font())
        return QSize(max(fm.horizontalAdvance(self.text()) + 36, 58), 30)

    def minimumSizeHint(self):
        return self.sizeHint()

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, e):
        c = COLORS
        dark = c.get("mode") == "dark"
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = r.height() / 2.0
        if self.isChecked():
            p.setPen(QPen(QColor(c["seg_edge"]), 1))
            p.setBrush(QColor(c["seg_sel"]))
            p.drawRoundedRect(r, radius, radius)
            fg = QColor(c["text"])
            f = self.font()
            f.setWeight(QFont.DemiBold)
            p.setFont(f)
        else:
            if self._hover:
                p.setPen(Qt.NoPen)
                p.setBrush(_c("#000000", 16) if not dark else _c("#ffffff", 26))
                p.drawRoundedRect(r, radius, radius)
            fg = QColor(c["text"] if self._hover else c["muted"])
            p.setFont(self.font())
        p.setPen(fg)
        p.drawText(self.rect(), Qt.AlignCenter, self.text())
        p.end()


class WinButton(QPushButton):
    """标题栏自绘按钮：最小化 / 最大化(还原) / 关闭 / 日夜切换。

    全部用 QPainter 矢量绘制，避免某个 Unicode 字形在雅黑里缺字、渲染成小方块。
    """

    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setObjectName("WinBtn")
        self.setFixedSize(38, 30)
        self.setCursor(Qt.ArrowCursor)
        self._hover = False
        self._maximized = False
        self.setFocusPolicy(Qt.NoFocus)

    def set_maximized(self, on):
        if on != self._maximized:
            self._maximized = on
            self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def _icon_color(self):
        if self.kind == "close" and self._hover:
            return QColor("white")
        return QColor(COLORS["text"])

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(4, 4, -4, -4)
        if self._hover:
            p.setPen(Qt.NoPen)
            if self.kind == "close":
                p.setBrush(QColor("#ff453a"))
            else:
                p.setBrush(QColor(COLORS["winbtn_hover"]))
            p.drawRoundedRect(r, 8, 8)
        pen = QPen(self._icon_color())
        pen.setWidthF(1.4)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        cx, cy = self.width() / 2, self.height() / 2

        if self.kind == "min":
            p.drawLine(QPointF(cx - 6, cy + 4), QPointF(cx + 6, cy + 4))
        elif self.kind == "max":
            if self._maximized:
                p.drawRoundedRect(QRectF(cx - 5, cy - 6, 9, 9), 2.0, 2.0)
                p.drawRoundedRect(QRectF(cx - 2.5, cy - 2.5, 9, 9), 2.0, 2.0)
            else:
                p.drawRoundedRect(QRectF(cx - 6, cy - 5, 12, 10), 2.4, 2.4)
        elif self.kind == "close":
            p.drawLine(QPointF(cx - 5, cy - 5), QPointF(cx + 5, cy + 5))
            p.drawLine(QPointF(cx + 5, cy - 5), QPointF(cx - 5, cy + 5))
        elif self.kind == "theme":
            # 白天模式画「月亮」（点击切到黑夜）；黑夜模式画「太阳」
            if COLORS.get("mode") == "dark":
                p.drawEllipse(QPointF(cx, cy), 4.2, 4.2)
                for k in range(8):
                    import math
                    a = k * math.pi / 4
                    p.drawLine(
                        QPointF(cx + math.cos(a) * 6.6, cy + math.sin(a) * 6.6),
                        QPointF(cx + math.cos(a) * 8.8, cy + math.sin(a) * 8.8))
            else:
                moon = QPainterPath()
                moon.addEllipse(QPointF(cx + 1.0, cy), 6.8, 6.8)
                cut = QPainterPath()
                cut.addEllipse(QPointF(cx + 4.4, cy - 1.8), 6.2, 6.2)
                p.drawPath(moon.subtracted(cut))
        p.end()


class ToggleSwitch(QCheckBox):
    """拨动开关（自绘）：轨道 + 白色滑钮，切换带平滑动画。

    QSS 无法绘制 indicator 的滑钮（只会得到一个空胶囊），因此自绘。
    """

    TW, TH, PAD = 46, 28, 3

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(self.TH)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet("background:transparent;")
        f = self.font()
        f.setPixelSize(13)
        f.setFamilies(["Segoe UI Variable Text", "Segoe UI",
                       "Microsoft YaHei UI", "Microsoft YaHei"])
        self.setFont(f)
        self._pos = 1.0 if self.isChecked() else 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(170)
        self._anim.valueChanged.connect(self._on_anim)
        self.toggled.connect(self._on_toggled)

    def _on_toggled(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def _on_anim(self, v):
        self._pos = float(v)
        self.update()

    def sizeHint(self):
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(self.font())
        return QSize(self.TW + 12 + fm.horizontalAdvance(self.text()), self.TH)

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, e):
        c = COLORS
        dark = c.get("mode") == "dark"
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        track = QRectF(0.5, 2.5, self.TW - 1, self.TH - 5)
        radius = track.height() / 2.0
        on = self._pos

        off_col = _c("#e8e8ed" if not dark else "#39393d", 255)
        on_col = QColor(c["accent"])
        col = QColor(off_col)
        col.setRed(int(off_col.red() + (on_col.red() - off_col.red()) * on))
        col.setGreen(int(off_col.green() + (on_col.green() - off_col.green()) * on))
        col.setBlue(int(off_col.blue() + (on_col.blue() - off_col.blue()) * on))
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(track, radius, radius)

        knob_d = track.height() - 3
        kx = track.left() + 1.5 + on * (track.width() - knob_d - 3)
        krect = QRectF(kx, track.top() + 1.5, knob_d, knob_d)
        p.setPen(QPen(_c("#000000", 26), 1))
        p.setBrush(QColor("white"))
        p.drawEllipse(krect)

        if self.text():
            p.setPen(QColor(c["text"]))
            p.setFont(self.font())
            p.drawText(QRectF(self.TW + 12, 0, self.width() - self.TW - 12, self.height()),
                       Qt.AlignLeft | Qt.AlignVCenter, self.text())
        p.end()


class StateIcon(QWidget):
    """关卡圆形状态图标：未开始(灰)/进行中(蓝脉冲)/成功(绿勾)/失败(红叉)。"""

    def __init__(self, number, size=44, parent=None):
        super().__init__(parent)
        self._number = number
        self._size = size
        self.setFixedSize(size, size)
        self._state = "pending"
        self._scale = 1.0
        self._pop = 1.0
        self._pulse = QVariantAnimation(self)
        self._pulse.setStartValue(0.0)
        self._pulse.setEndValue(1.0)
        self._pulse.setDuration(1600)
        self._pulse.setLoopCount(-1)
        self._pulse.valueChanged.connect(self.update)
        self._pop_anim = QVariantAnimation(self)
        self._pop_anim.setStartValue(0.55)
        self._pop_anim.setEndValue(1.0)
        self._pop_anim.setDuration(360)
        self._pop_anim.valueChanged.connect(self._on_pop)

    def _on_pop(self, v):
        # ease-out back 弹性
        t = v
        s = 1.70158
        t1 = t - 1
        self._pop = 1 + (s + 1) * t1 ** 3 + s * t1 ** 2
        self.update()

    def state(self):
        return self._state

    def set_state(self, state):
        if state == self._state:
            return
        self._state = state
        if state == "active":
            self._pulse.start()
        else:
            self._pulse.stop()
        self._pop_anim.stop()
        self._pop_anim.start()
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx = cy = self._size / 2
        base_r = self._size * 0.40 * self._pop
        state_colors = {
            "pending": COLORS["pending"], "active": COLORS["accent"],
            "ok": COLORS["ok"], "fail": COLORS["error"],
        }
        col = QColor(state_colors[self._state])

        # 进行中：极细脉冲扩散环
        if self._state == "active":
            v = self._pulse.currentValue()
            for k in (0.0, 0.5):
                ph = (v + k) % 1.0
                rr = base_r + ph * (self._size * 0.16)
                alpha = int(110 * (1 - ph))
                p.setPen(QPen(_c(COLORS["accent"], alpha), 1.4))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(cx, cy), rr, rr)

        if self._state == "pending":
            p.setPen(QPen(_c(state_colors["pending"], 230), 1.6))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, cy), base_r, base_r)
        elif self._state == "active":
            p.setPen(QPen(col, 1.8))
            p.setBrush(_c(COLORS["accent"], 30))
            p.drawEllipse(QPointF(cx, cy), base_r, base_r)
        else:
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(col))
            p.drawEllipse(QPointF(cx, cy), base_r, base_r)

        # 图标
        pen = QPen()
        pen.setWidthF(2.2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        if self._state == "ok":
            pen.setColor(QColor("white"))
            p.setPen(pen)
            d = base_r * 0.34
            path = QPainterPath()
            path.moveTo(cx - d * 1.05, cy + d * 0.05)
            path.lineTo(cx - d * 0.25, cy + d * 0.85)
            path.lineTo(cx + d * 1.15, cy - d * 0.72)
            p.drawPath(path)
        elif self._state == "fail":
            pen.setColor(QColor("white"))
            p.setPen(pen)
            d = base_r * 0.34
            p.drawLine(QPointF(cx - d, cy - d), QPointF(cx + d, cy + d))
            p.drawLine(QPointF(cx + d, cy - d), QPointF(cx - d, cy + d))
        else:
            p.setPen(QColor(col if self._state == "active" else COLORS["muted"]))
            f = QFont()
            f.setPixelSize(13)
            f.setBold(True)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignCenter, str(self._number))
        p.end()


class PulseDot(QWidget):
    """服务状态小圆点。"""

    def __init__(self, size=9, parent=None):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)
        self._color = COLORS["pending"]
        self._on = False
        self._v = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(1200)
        self._anim.setLoopCount(-1)
        self._anim.valueChanged.connect(self.update)

    def set_status(self, color, pulse=False):
        self._color = color
        if pulse != self._on:
            self._on = pulse
            if pulse:
                self._anim.start()
            else:
                self._anim.stop()
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx = cy = self._size / 2
        r = self._size * 0.32
        if self._on:
            v = self._anim.currentValue()
            rr = r + v * self._size * 0.36
            p.setPen(QPen(_c(self._color, int(110 * (1 - v))), 1.2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, cy), rr, rr)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(self._color)))
        p.drawEllipse(QPointF(cx, cy), r, r)
        p.end()


class ServicePill(QFrame):
    """服务状态行：圆点 + 名称 + 状态文字（发丝描边的玻璃胶囊）。"""

    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.setObjectName("StatusPill")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 9, 14, 9)
        lay.setSpacing(9)
        self.dot = PulseDot(9)
        self.dot.set_status(COLORS["pending"])
        self.label = QLabel(name)
        self.label.setStyleSheet("font-weight:500; background:transparent;")
        self.sub = QLabel("未运行")
        self.sub.setStyleSheet("color:%s; background:transparent;font-size:12px;"
                               % COLORS["muted"])
        lay.addWidget(self.dot)
        lay.addWidget(self.label)
        lay.addStretch()
        lay.addWidget(self.sub)
        self._state, self._text = "stop", "未运行"

    def retheme(self):
        self.set_state(self._state, self._text)

    def set_state(self, state, text):
        self._state, self._text = state, text
        mapping = {
            "stop": (COLORS["pending"], False),
            "run": (COLORS["ok"], True),
            "busy": (COLORS["accent"], True),
            "error": (COLORS["error"], False),
        }
        col, pulse = mapping.get(state, mapping["stop"])
        self.dot.set_status(col, pulse)
        self.sub.setText(text)
        self.sub.setStyleSheet("color:%s; background:transparent;font-size:12px;" % col)


class DeviceChip(QLabel):
    """设备标签：统一灰阶，仅用深浅区分设备（不引入第二种品牌色）。"""

    def __init__(self, device_key, text=None, parent=None):
        super().__init__(parent)
        self._dev = device_key
        self._name = text
        self.setAlignment(Qt.AlignCenter)
        self.set_device(device_key, text)

    def retheme(self):
        self.set_device(self._dev, self._name)

    def set_device(self, device_key, text=None):
        self._dev = device_key
        if text is not None:
            self._name = text
        color = DEVICE_COLORS.get(device_key, COLORS["muted"])
        name = self._name or device_key
        if COLORS.get("mode") == "dark":
            bg = _c(color, 34).name(QColor.HexArgb)
            bd = _c(color, 52).name(QColor.HexArgb)
        else:
            bg = "rgba(0,0,0,16)"
            bd = "rgba(0,0,0,26)"
        self.setStyleSheet(
            "background:%s;color:%s;border:1px solid %s;border-radius:11px;"
            "padding:3px 10px;font-size:11px;font-weight:500;"
            % (bg, color, bd))
        self.setText(name)


class GateCard(QFrame):
    """开播关卡卡片：玻璃卡 + 发丝描边；状态用图标与描边色轻提示。"""

    clicked = Signal(str)

    def __init__(self, idx, gate, parent=None):
        super().__init__(parent)
        self.gate_id = gate["id"]
        self.setObjectName("GateCard")
        self.setFixedHeight(126)
        self.setCursor(Qt.PointingHandCursor)
        self._status = "pending"
        self._apply_style()
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)
        top = QHBoxLayout()
        top.setSpacing(8)
        self.icon = StateIcon(idx, 40)
        self.chip = DeviceChip(gate["device"], DEVICES.get(gate["device"], gate["device"]))
        top.addWidget(self.icon)
        top.addStretch()
        top.addWidget(self.chip, 0, Qt.AlignTop)
        v.addLayout(top)
        self.title = QLabel(gate["title"])
        self.title.setStyleSheet("font-weight:600;font-size:13px;background:transparent;")
        self.detail = QLabel(gate["wait"])
        self.detail.setStyleSheet("color:%s;font-size:12px;background:transparent;"
                                  % COLORS["muted"])
        self.detail.setWordWrap(True)
        v.addWidget(self.title)
        v.addWidget(self.detail)
        v.addStretch()

    def _border_color(self, status):
        # 未开始时为发丝灰；有状态时才着色，且降低饱和度以示克制
        return {"pending": COLORS["edge"], "active": COLORS["accent"],
                "ok": COLORS["ok"], "fail": COLORS["error"]}.get(status, COLORS["edge"])

    def _apply_style(self):
        border = self._border_color(self._status)
        self.setStyleSheet(
            "QFrame#GateCard{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 %s,stop:1 %s);border:1px solid %s;"
            "border-radius:%dpx;}"
            % (COLORS["gate_top"], COLORS["gate_bot"], border, R_CARD))

    def retheme(self):
        self.detail.setStyleSheet("color:%s;font-size:12px;background:transparent;"
                                  % COLORS["muted"])
        self.chip.retheme()
        self._apply_style()
        self.update()

    def set_state(self, status, detail):
        self._status = status
        self.icon.set_state(status)
        self.detail.setText(detail)
        self._apply_style()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.gate_id)


class ProgressBar(QWidget):
    """圆角进度条，数值变化带平滑动画（品牌蓝单色）。"""

    def __init__(self, parent=None, h=6):
        super().__init__(parent)
        self.setFixedHeight(h)
        self._value = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(420)
        self._anim.valueChanged.connect(self._on_anim)

    def set_value(self, v, animate=True):
        v = max(0.0, min(1.0, v))
        if not animate:
            self._value = v
            self.update()
            return
        self._anim.stop()
        self._anim.setStartValue(self._value)
        self._anim.setEndValue(v)
        self._anim.start()

    def _on_anim(self, v):
        self._value = float(v)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.height() / 2
        p.setPen(Qt.NoPen)
        p.setBrush(_c(COLORS["card3"], 255))
        p.drawRoundedRect(self.rect(), r, r)
        if self._value > 0:
            w = self.width() * self._value
            g = QLinearGradient(0, 0, self.width(), 0)
            g.setColorAt(0, QColor(COLORS["accent"]))
            g.setColorAt(1, QColor(COLORS["accent_hover"]))
            p.setBrush(QBrush(g))
            p.drawRoundedRect(QRectF(0, 0, w, self.height()), r, r)
        p.end()


class TaskThread(QThread):
    """通用后台任务：fn(*args)，完成后发 result。"""
    result = Signal(object)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            self.result.emit(self.fn(*self.args, **self.kwargs))
        except Exception as ex:
            self.result.emit({"__error__": str(ex)})


class LogConsole(QPlainTextEdit):
    """日志控制台。

    日志用富文本渲染，颜色是「写死」在 HTML 里的；若只依赖 QSS 换肤，
    切换主题后旧日志会保留旧主题的文字颜色（深色模式写的浅灰字落到白色底上就
    完全看不见）。因此这里把原始日志行缓存下来，主题切换 / 切换筛选时整体重放。
    """

    MAX_ROWS = 3000

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LogView")
        self.setReadOnly(True)
        self.setMaximumBlockCount(5000)
        self.setPlaceholderText("暂无日志。")
        self._filter = "全部"
        self._rows = []

    def set_filter(self, source):
        self._filter = source
        self._replay()

    def clear(self):
        self._rows = []
        super().clear()

    def retheme(self):
        """按当前主题重放全部日志（修复换肤后旧日志文字不可读）。"""
        self._replay()

    def append(self, level, source, msg):
        row = (datetime.now().strftime("%H:%M:%S"), level, str(source), str(msg))
        self._rows.append(row)
        if len(self._rows) > self.MAX_ROWS:
            del self._rows[:len(self._rows) - self.MAX_ROWS]
        if self._filter != "全部" and row[2] != self._filter:
            return
        self._write_row(row)

    # ---- 内部 ----
    def _replay(self):
        sb = self.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 40
        super().clear()
        for row in self._rows:
            if self._filter == "全部" or row[2] == self._filter:
                self._write_row(row, autoscroll=False)
        if at_bottom:
            sb.setValue(sb.maximum())

    def _write_row(self, row, autoscroll=True):
        ts, level, source, msg = row
        col = level_color(level)
        tag = {"ok": "●", "warn": "▲", "error": "✖", "info": "·", "": "·"}.get(level, "·")
        html = ('<span style="color:%s;">%s</span> '
                '<span style="color:%s;font-weight:600;">%s</span> '
                '<span style="color:%s;">%s</span> '
                '<span style="color:%s;">%s</span>'
                % (COLORS["faint"], ts, col, tag, _c(col, 210).name(),
                   _esc(source), COLORS["log_text"], _esc(msg)))
        self.appendHtml(html)
        if autoscroll:
            sb = self.verticalScrollBar()
            if sb.value() > sb.maximum() - 80:
                sb.setValue(sb.maximum())


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
