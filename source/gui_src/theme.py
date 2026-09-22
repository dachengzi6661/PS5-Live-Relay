# -*- coding: utf-8 -*-
"""极简主题：极致极简 · 玻璃质感。

设计准则
--------
- 纯白背景、超大面积留白、居中对称；字体层级清晰（系统无衬线字体栈，中文回落微软雅黑）。
- 唯一品牌色：品牌蓝 #0071E3 —— 只用于主按钮与交互元素（焦点、选中、链接）。
  其余一律黑白灰；状态语义色沿用 系统色（仅用于「5 关」成败提示）。
- 导航栏 / 卡片 / 按钮均为「玻璃质感」：半透明白 + 顶部 1px 高光 + 极细描边，
  真实高斯模糊由 wineffects.enable_acrylic() 在 Windows 上尽力开启。
- 控件形态：胶囊主按钮（border-radius = 高度一半）、连续曲率圆角卡片（20px）。

结构约定（与旧版保持一致，避免调用方改动）
------------------------------------------
- COLORS / DEVICE_COLORS 始终指向「当前生效」的调色板（原地 update）。
- build_qss() 按当前调色板动态生成样式表；切换主题时重新 app.setStyleSheet。
"""

# ---------------------------------------------------------------------------
# 字体栈：系统无衬线 → 中文微软雅黑
# ---------------------------------------------------------------------------
FONT_STACK = ("'Segoe UI Variable Display','Segoe UI Variable Text','Segoe UI',"
              "'Microsoft YaHei UI','Microsoft YaHei',"
              "system-ui,sans-serif")
MONO_STACK = ("'Cascadia Mono','Cascadia Code',"
              "'Consolas','Courier New',monospace")

# 圆角规范（连续曲率近似）
R_SHELL = 20      # 主窗外壳
R_CARD = 20       # 卡片
R_INPUT = 12      # 输入框
R_CHIP = 18       # 胶囊（普通按钮，高度约 36px）
R_PILL = 24       # 大胶囊（主按钮，高度约 46px）
R_SEG = 16        # 分段控件

# ---------------------------------------------------------------------------
# 调色板
# ---------------------------------------------------------------------------
# 白天：纯白（默认）
# 黑夜：深色（近黑 #000 / #1d1d1f），同一套蓝色
_LIGHT = {
    "mode": "light",
    # —— 基础实色（自绘控件 / 兜底）
    "bg":       "#ffffff",
    "bg2":      "#fbfbfd",
    "card":     "#ffffff",
    "card2":    "#f5f5f7",
    "card3":    "#e8e8ed",
    "border":   "#d2d2d7",
    "border2":  "#86868b",
    # —— 文字
    "text":     "#1d1d1f",
    "muted":    "#6e6e73",
    "faint":    "#86868b",
    # —— 品牌色 / 语义色（浅色可读版本）
    "accent":   "#0071e3",
    "accent2":  "#0071e3",
    "accent_hover": "#0077ed",
    "accent_press": "#006edb",
    "accent_soft":  "rgba(0,113,227,26)",
    "ok":       "#248a3d",
    "warn":     "#c93400",
    "error":    "#d70015",
    "pending":  "#aeaeb2",
    # —— 玻璃 / QSS
    "win_base": "rgba(240,240,243,236)",   # 窗口底（保留一丝通透，不做系统级模糊）
    "win_bg":   "rgba(240,240,243,244)",   # 外壳底色：页面浅灰，比纯白卡片低一档
    "dlg_bg":   "#ffffff",
    "nav_bg":   "rgba(255,255,255,208)",   # 顶部导航玻璃质感（磨砂白）
    "nav_bot":  "rgba(250,250,252,168)",
    "nav_edge": "rgba(0,0,0,24)",
    "seg_track": "rgba(0,0,0,15)",         # 分段控件轨道
    "seg_sel":  "#ffffff",                 # 选中胶囊
    "seg_edge": "rgba(0,0,0,20)",
    "card_top": "rgba(255,255,255,255)",
    "card_bot": "rgba(253,253,254,255)",
    "hero_top": "rgba(255,255,255,255)",
    "hero_bot": "rgba(251,251,253,255)",
    "gate_top": "rgba(255,255,255,255)",
    "gate_bot": "rgba(252,252,254,255)",
    "panel_top":"rgba(255,255,255,255)",
    "panel_bot":"rgba(250,250,252,255)",
    "pill_bg":  "rgba(255,255,255,214)",
    "pill_edge":"rgba(0,0,0,26)",
    "edge":     "rgba(0,0,0,22)",
    "edge_hi":  "rgba(255,255,255,255)",
    "hairline": "rgba(0,0,0,26)",
    # —— 控件
    "btn_bg":   "rgba(255,255,255,0)",
    "btn_hover":"rgba(0,0,0,16)",
    "btn_press":"rgba(0,0,0,28)",
    "btn_ghost_edge": "rgba(0,0,0,48)",
    "winbtn_hover": "rgba(0,0,0,22)",
    "input_bg": "#f5f5f7",
    "input_edge":"rgba(0,0,0,30)",
    "item_hover":"rgba(0,113,227,26)",
    "alt_row":  "rgba(0,0,0,10)",
    "combo_bg": "#ffffff",
    "combo_sel":"rgba(0,113,227,30)",
    "header_bg":"#f5f5f7",
    "log_bg":   "#f5f5f7",
    "log_text": "#1d1d1f",
    "track":    "rgba(0,0,0,52)",
    "track_hi": "rgba(0,0,0,88)",
    "dis_bg":   "rgba(0,0,0,18)",
    "dis_fg":   "#aeaeb2",
    "shadow":   "rgba(0,0,0,64)",
    "acrylic":  "rgba(255,255,255,150)",
    "img_tint": "rgba(255,255,255,235)",
}

_DARK = {
    "mode": "dark",
    "bg":       "#000000",
    "bg2":      "#0a0a0b",
    "card":     "#1c1c1e",
    "card2":    "#2c2c2e",
    "card3":    "#3a3a3c",
    "border":   "#38383a",
    "border2":  "#5a5a5e",
    "text":     "#f5f5f7",
    "muted":    "#a1a1a6",
    "faint":    "#86868b",
    "accent":   "#0a84ff",
    "accent2":  "#0a84ff",
    "accent_hover": "#3096ff",
    "accent_press": "#0071e3",
    "accent_soft":  "rgba(10,132,255,44)",
    "ok":       "#30d158",
    "warn":     "#ff9f0a",
    "error":    "#ff453a",
    "pending":  "#48484a",
    "win_base": "rgba(10,10,11,238)",
    "win_bg":   "rgba(10,10,11,246)",
    "dlg_bg":   "#1c1c1e",
    "nav_bg":   "rgba(28,28,30,190)",
    "nav_bot":  "rgba(24,24,26,150)",
    "nav_edge": "rgba(255,255,255,26)",
    "seg_track": "rgba(255,255,255,22)",
    "seg_sel":  "rgba(120,120,128,96)",
    "seg_edge": "rgba(255,255,255,20)",
    "card_top": "rgba(255,255,255,14)",
    "card_bot": "rgba(255,255,255,6)",
    "hero_top": "rgba(255,255,255,18)",
    "hero_bot": "rgba(255,255,255,7)",
    "gate_top": "rgba(255,255,255,15)",
    "gate_bot": "rgba(255,255,255,6)",
    "panel_top":"rgba(255,255,255,12)",
    "panel_bot":"rgba(255,255,255,5)",
    "pill_bg":  "rgba(255,255,255,18)",
    "pill_edge":"rgba(255,255,255,34)",
    "edge":     "rgba(255,255,255,26)",
    "edge_hi":  "rgba(255,255,255,52)",
    "hairline": "rgba(255,255,255,26)",
    "btn_bg":   "rgba(255,255,255,0)",
    "btn_hover":"rgba(255,255,255,26)",
    "btn_press":"rgba(255,255,255,14)",
    "btn_ghost_edge": "rgba(255,255,255,64)",
    "winbtn_hover": "rgba(255,255,255,30)",
    "input_bg": "rgba(255,255,255,14)",
    "input_edge":"rgba(255,255,255,44)",
    "item_hover":"rgba(10,132,255,52)",
    "alt_row":  "rgba(255,255,255,10)",
    "combo_bg": "#2c2c2e",
    "combo_sel":"rgba(10,132,255,90)",
    "header_bg":"#2c2c2e",
    "log_bg":   "rgba(255,255,255,12)",
    "log_text": "#e5e5ea",
    "track":    "rgba(255,255,255,54)",
    "track_hi": "rgba(255,255,255,96)",
    "dis_bg":   "rgba(255,255,255,12)",
    "dis_fg":   "#6e6e73",
    "shadow":   "rgba(0,0,0,190)",
    "acrylic":  "rgba(28,28,30,110)",
    "img_tint": "rgba(28,28,30,0)",
}

PALETTES = {"白天": _LIGHT, "黑夜": _DARK}

# 当前生效调色板（保持同一 dict 对象，原地更新，旧引用也能拿到新值）
COLORS = dict(_LIGHT)
_mode = "白天"

# 设备标签：极简克制 —— 统一灰阶，仅用深浅区分，不引入第二种品牌色
_DEVICE_LIGHT = {
    "pc":      "#3a3a3c",
    "network": "#48484a",
    "ps5":     "#555557",
    "accel":   "#636366",
    "backend": "#6e6e73",
    "config":  "#7c7c80",
    "dns":     "#48484a",
    "mtx":     "#555557",
}
_DEVICE_DARK = {
    "pc":      "#d1d1d6",
    "network": "#c7c7cc",
    "ps5":     "#b8b8bd",
    "accel":   "#a1a1a6",
    "backend": "#9a9aa0",
    "config":  "#8e8e93",
    "dns":     "#c7c7cc",
    "mtx":     "#b8b8bd",
}
DEVICE_PALETTES = {"白天": _DEVICE_LIGHT, "黑夜": _DEVICE_DARK}
DEVICE_COLORS = dict(_DEVICE_LIGHT)


def active_mode():
    return _mode


def set_active(mode):
    """切换当前调色板（原地更新 COLORS / DEVICE_COLORS）。"""
    global _mode
    if mode not in PALETTES:
        mode = "白天"
    _mode = mode
    COLORS.clear()
    COLORS.update(PALETTES[mode])
    DEVICE_COLORS.clear()
    DEVICE_COLORS.update(DEVICE_PALETTES[mode])
    return mode


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def lerp_color(c1, c2, t):
    a, b = hex_to_rgb(c1), hex_to_rgb(c2)
    r = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
    return "#%02x%02x%02x" % r


# ---------------------------------------------------------------------------
# 样式表
# ---------------------------------------------------------------------------
def build_qss():
    c = dict(COLORS)
    return """
* { font-family: %(font)s; }
QWidget { color: %(text)s; background: transparent; font-size: 13px; }
QMainWindow#MainWindow, QWidget#MainWindow { background: transparent; border: none; }

/* ===== 玻璃质感外壳：极细描边 + 顶部高光，柔和外投影由代码设置 ===== */
QFrame#GlassShell {
    background: %(win_bg)s;
    border: 1px solid %(edge)s;
    border-radius: %(r_shell)dpx;
}

/* ===== 顶部导航（玻璃质感，底部发丝线分隔） ===== */
QFrame#TopNav {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 %(nav_bg)s, stop:1 %(nav_bot)s);
    border: none;
    border-bottom: 1px solid %(nav_edge)s;
    border-top-left-radius: %(r_shell)dpx;
    border-top-right-radius: %(r_shell)dpx;
}
QLabel#NavTitle { font-size: 14px; font-weight: 600; letter-spacing: 0.2px; color: %(text)s; }
QLabel#NavMark  { font-size: 12px; color: %(faint)s; }

/* 分段控件（居中对称） */
QFrame#SegTrack {
    background: %(seg_track)s;
    border: 1px solid %(seg_edge)s;
    border-radius: %(r_seg)dpx;
}
QPushButton#SegBtn {
    background: transparent; border: none; border-radius: %(r_seg)dpx;
    padding: 6px 16px; color: %(muted)s; font-size: 13px; font-weight: 500;
    min-width: 46px;
}
QPushButton#SegBtn:hover { color: %(text)s; background: %(btn_hover)s; }
QPushButton#SegBtn:checked {
    background: %(seg_sel)s; color: %(text)s; font-weight: 600;
    border: 1px solid %(seg_edge)s;
}

/* ===== 卡片：玻璃质感，连续曲率圆角 ===== */
QFrame#Card, QFrame#PanelCard, QFrame#GateCard, QFrame#HeroCard {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 %(card_top)s, stop:1 %(card_bot)s);
    border: 1px solid %(edge)s;
    border-radius: %(r_card)dpx;
}
QFrame#HeroCard {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 %(hero_top)s, stop:1 %(hero_bot)s);
    border: 1px solid %(edge)s;
    border-radius: 24px;
}
QFrame#Divider { background: %(hairline)s; border: none; max-height: 1px; }
QFrame#VDivider { background: %(hairline)s; border: none; max-width: 1px; }

/* ===== 文字层级 ===== */
QLabel { background: transparent; }
QLabel#H1 { font-size: 34px; font-weight: 700; }
QLabel#H2 { font-size: 20px; font-weight: 700; }
QLabel#H3 { font-size: 15px; font-weight: 600; }
QLabel#Sub { font-size: 15px; color: %(muted)s; }
QLabel#Muted { color: %(muted)s; }
QLabel#Faint { color: %(faint)s; font-size: 12px; }
QLabel#BigIp { font-size: 34px; font-weight: 700; color: %(text)s; }
QLabel#Value { font-size: 15px; font-weight: 600; }
QLabel#HeroKicker { font-size: 12px; font-weight: 600; color: %(faint)s; }

/* ===== 按钮：胶囊 / 玻璃质感 ===== */
QPushButton {
    background: %(btn_bg)s;
    border: 1px solid %(btn_ghost_edge)s;
    border-radius: %(r_chip)dpx;
    padding: 7px 16px; color: %(text)s; font-size: 13px; font-weight: 500;
    min-height: 20px;
}
QPushButton:hover { background: %(btn_hover)s; }
QPushButton:pressed { background: %(btn_press)s; }
QPushButton:disabled { color: %(dis_fg)s; border-color: %(edge)s; background: transparent; }

/* 主按钮：品牌蓝胶囊 */
QPushButton#Primary {
    background: %(accent)s; color: #ffffff; border: 1px solid transparent;
    font-size: 15px; font-weight: 600; padding: 12px 30px;
    border-radius: %(r_pill)dpx;
}
QPushButton#Primary:hover { background: %(accent_hover)s; }
QPushButton#Primary:pressed { background: %(accent_press)s; }
QPushButton#Primary:disabled { background: %(dis_bg)s; color: %(dis_fg)s; }

/* 次按钮：中性玻璃胶囊（克制，不用红色） */
QPushButton#Stop {
    background: transparent; color: %(text)s;
    border: 1px solid %(btn_ghost_edge)s;
    font-size: 15px; font-weight: 600; padding: 12px 30px;
    border-radius: %(r_pill)dpx;
}
QPushButton#Stop:hover { background: %(btn_hover)s; }
QPushButton#Stop:pressed { background: %(btn_press)s; }
QPushButton#Stop:disabled { color: %(dis_fg)s; border-color: %(edge)s; background: transparent; }

QPushButton#Ghost { background: transparent; border: 1px solid %(btn_ghost_edge)s; }
QPushButton#Link {
    background: transparent; border: none; padding: 2px 0; color: %(accent)s;
    font-weight: 500;
}
QPushButton#Link:hover { color: %(accent_hover)s; }
QPushButton#Chip {
    background: %(btn_bg)s; border: 1px solid %(btn_ghost_edge)s;
    padding: 8px 16px; border-radius: %(r_chip)dpx; color: %(text)s; font-weight: 500;
}
QPushButton#Chip:hover { border-color: transparent; background: %(accent)s; color: #ffffff; }
QPushButton#Chip:pressed { background: %(accent_press)s; color: #ffffff; }

/* ===== 输入：浅灰填充 + 蓝环焦点 ===== */
QLineEdit, QComboBox, QPlainTextEdit, QTextEdit {
    background: %(input_bg)s; border: 1px solid %(input_edge)s;
    border-radius: %(r_input)dpx; padding: 9px 12px; color: %(text)s;
    selection-background-color: %(accent)s; selection-color: #ffffff;
}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus {
    border: 2px solid %(accent)s; padding: 8px 11px; background: %(card)s;
}
QLineEdit:disabled, QComboBox:disabled { color: %(dis_fg)s; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox::down-arrow { width: 0; height: 0; }
QComboBox QAbstractItemView {
    background: %(combo_bg)s; border: 1px solid %(edge)s; color: %(text)s;
    selection-background-color: %(combo_sel)s; border-radius: 12px; outline: none;
    padding: 6px;
}

/* ===== 开关 ===== */
QCheckBox#Switch { spacing: 10px; background: transparent; }
QCheckBox#Switch::indicator { width: 44px; height: 26px; border-radius: 13px;
    background: %(card3)s; border: 1px solid %(edge)s; }
QCheckBox#Switch::indicator:checked { background: %(accent)s; border-color: %(accent)s; }

/* ===== 滚动条：隐形轨道，悬停才见 ===== */
QScrollBar:vertical { background: transparent; width: 11px; margin: 4px 2px; }
QScrollBar::handle:vertical { background: %(track)s; border-radius: 4px; min-height: 40px; }
QScrollBar::handle:vertical:hover { background: %(track_hi)s; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 11px; margin: 2px 4px; }
QScrollBar::handle:horizontal { background: %(track)s; border-radius: 4px; min-width: 40px; }
QScrollBar::handle:horizontal:hover { background: %(track_hi)s; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
QScrollArea { border: none; background: transparent; }
QAbstractScrollArea::corner { background: transparent; border: none; }

/* ===== 列表 / 表格 ===== */
QListWidget, QTreeWidget, QTableWidget {
    background: transparent; border: 1px solid %(edge)s; border-radius: 16px;
    alternate-background-color: %(alt_row)s; color: %(text)s; outline: none;
    padding: 4px;
}
QListWidget::item, QTreeWidget::item { padding: 8px 8px; border-radius: 10px; }
QListWidget::item:hover, QTreeWidget::item:hover { background: %(btn_hover)s; }
QListWidget::item:selected, QTreeWidget::item:selected {
    background: %(combo_sel)s; color: %(text)s;
}
QHeaderView::section { background: transparent; border: none; padding: 8px 10px;
    color: %(muted)s; font-weight: 600; border-bottom: 1px solid %(hairline)s; }
QTableWidget { gridline-color: %(hairline)s; }
QTableCornerButton::section { background: transparent; border: none; }

/* ===== 日志 ===== */
QPlainTextEdit#LogView {
    background: %(log_bg)s; color: %(log_text)s; border: 1px solid %(edge)s;
    border-radius: 16px; padding: 10px;
    font-family: %(mono)s; font-size: 12px;
}

/* ===== 徽章 / 浮层 ===== */
QFrame#StatusPill {
    background: %(pill_bg)s; border: 1px solid %(pill_edge)s; border-radius: %(r_chip)dpx;
}
QFrame#DeviceChipBox { background: transparent; border: none; }
QToolTip { background: %(dlg_bg)s; color: %(text)s; border: 1px solid %(edge)s;
    padding: 6px 10px; border-radius: 10px; }
QMenu { background: %(dlg_bg)s; border: 1px solid %(edge)s; border-radius: 14px;
    padding: 6px; color: %(text)s; }
QMenu::item { padding: 8px 24px; border-radius: 10px; background: transparent; }
QMenu::item:selected { background: %(accent)s; color: #ffffff; }
QMenu::separator { height: 1px; background: %(hairline)s; margin: 6px 10px; }
QMessageBox, QDialog { background: %(dlg_bg)s; }
QGroupBox { border: 1px solid %(edge)s; border-radius: 16px; margin-top: 14px;
    padding-top: 14px; font-weight: 600; background: transparent; }
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px;
    color: %(muted)s; background: transparent; }
QCheckBox, QRadioButton { background: transparent; }
""" % dict(c, font=FONT_STACK, mono=MONO_STACK,
           r_shell=R_SHELL, r_card=R_CARD, r_input=R_INPUT,
           r_chip=R_CHIP, r_pill=R_PILL, r_seg=R_SEG)


# 兼容旧入口
QSS = build_qss()


def apply_theme(app, win=None, mode="白天"):
    """切换主题：更新调色板 → 重放全局样式 → 刷新自绘控件。"""
    set_active(mode)
    if app is not None:
        app.setStyleSheet(build_qss())
    if win is not None:
        if hasattr(win, "retheme"):
            win.retheme()
    return mode


def level_color(level):
    return {"ok": COLORS["ok"], "warn": COLORS["warn"], "error": COLORS["error"],
            "info": COLORS["accent2"], "": COLORS["muted"]}.get(level, COLORS["muted"])
