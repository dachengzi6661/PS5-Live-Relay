# -*- coding: utf-8 -*-
"""Windows 桌面效果：尽力为无边框窗口开启 Acrylic（亚克力 / 磨砂玻璃）背景模糊，
并设置 Win11 圆角。任何失败都安静回退（返回 False），由 Qt 半透明层保证外观。"""
import sys


def _enabled():
    return sys.platform == "win32"


def _extend_frame(hwnd):
    """把 DWM 帧扩展到整个客户区，亚克力模糊才能盖住无边框窗口。"""
    try:
        import ctypes
        dwm = ctypes.windll.dwmapi

        class MARGINS(ctypes.Structure):
            _fields_ = [("cxLeftWidth", ctypes.c_int),
                        ("cxRightWidth", ctypes.c_int),
                        ("cyTopHeight", ctypes.c_int),
                        ("cyBottomHeight", ctypes.c_int)]

        m = MARGINS(-1, -1, -1, -1)
        hr = dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(m))
        return hr == 0
    except Exception:
        return False


def _set_accent(hwnd, color, alpha):
    """通过未文档化的 SetWindowCompositionAttribute 开 ACCENT_ENABLE_ACRYLICBLURBEHIND。"""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    set_attr = getattr(user32, "SetWindowCompositionAttribute", None)
    if set_attr is None:
        return False

    class ACCENTPOLICY(ctypes.Structure):
        _fields_ = [("AccentState", ctypes.c_uint),
                    ("AccentFlags", ctypes.c_uint),
                    ("GradientColor", ctypes.c_uint),
                    ("AnimationId", ctypes.c_uint)]

    class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
        _fields_ = [("Attribute", ctypes.c_int),
                    ("Data", ctypes.POINTER(ctypes.c_int)),
                    ("SizeOfData", ctypes.c_size_t)]

    # GradientColor 为 0xAABBGGRR
    gradient = ((int(alpha) & 0xFF) << 24) | \
               ((int(color.blue()) & 0xFF) << 16) | \
               ((int(color.green()) & 0xFF) << 8) | \
               (int(color.red()) & 0xFF)

    accent = ACCENTPOLICY()
    accent.AccentState = 4          # ACCENT_ENABLE_ACRYLICBLURBEHIND（Win10 1803+ / Win11）
    accent.AccentFlags = 2          # 画到所有边框
    accent.GradientColor = gradient
    accent.AnimationId = 0

    data = WINDOWCOMPOSITIONATTRIBDATA()
    data.Attribute = 19             # WCA_ACCENT_POLICY
    data.SizeOfData = ctypes.sizeof(accent)
    data.Data = ctypes.cast(ctypes.pointer(accent), ctypes.POINTER(ctypes.c_int))
    set_attr.argtypes = [wintypes.HWND, ctypes.POINTER(WINDOWCOMPOSITIONATTRIBDATA)]
    try:
        return bool(set_attr(hwnd, ctypes.byref(data)))
    except Exception:
        return False


def _rounded_corners(hwnd):
    """Win11：DWMWA_WINDOW_CORNER_PREFERENCE = 33，DWMWCP_ROUND = 2。"""
    try:
        import ctypes
        dwm = ctypes.windll.dwmapi
        pref = ctypes.c_int(2)
        dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref),
                                  ctypes.sizeof(pref))
    except Exception:
        pass


def enable_acrylic(hwnd, color, alpha=0x33):
    """对窗口 HWND 开启亚克力模糊。成功返回 True，否则 False（调用方应走不透明回退）。"""
    if not _enabled() or hwnd is None:
        return False
    try:
        _extend_frame(hwnd)
        ok = _set_accent(hwnd, color, alpha)
        _rounded_corners(hwnd)
        return ok
    except Exception:
        return False
