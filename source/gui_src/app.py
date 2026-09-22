# -*- coding: utf-8 -*-
"""PS5 直播推流助手 · 入口：启动动画 → 主窗口。"""
import os
import sys

# 第一件事：关闭 PyInstaller 打包时的“静态启动图”（--splash 生成的那个窗口）。
# 它在 onefile 解压阶段显示，无关闭按钮、不能拖动；Python 启动后必须显式关闭，
# 否则它会一直停留在屏幕上。非打包环境没有 pyi_splash 模块，忽略即可。
try:
    import pyi_splash  # type: ignore
    pyi_splash.close()
except Exception:
    pass

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QSharedMemory
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QFont, QIcon

import theme
from splash import Splash
from main_window import MainWindow
import core


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("PS5 直播推流助手")
    app.setApplicationDisplayName("PS5 直播推流助手")

    # 主题：环境变量(自测) > 配置文件 > 默认白天（极简风格的纯白）
    try:
        _mode = os.environ.get("PS5LIVE_THEME") or core.load_config().get("主题", "白天")
    except Exception:
        _mode = "白天"
    if _mode not in theme.PALETTES:
        _mode = "白天"
    theme.set_active(_mode)
    app.setStyleSheet(theme.build_qss())
    # 字体：系统无衬线优先，中文回落微软雅黑
    f = QFont()
    f.setFamilies(["Segoe UI Variable Display", "Segoe UI Variable Text",
                   "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei"])
    f.setPixelSize(13)
    f.setHintingPreference(QFont.PreferFullHinting)
    app.setFont(f)
    app.setQuitOnLastWindowClosed(False)

    icon = core.resource_path("assets", "app.ico")
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))

    # 单实例保护（避免两个实例抢 53/1935 端口）
    shared = QSharedMemory("ps5live_stream_assistant_singleton")
    if not shared.create(1):
        QMessageBox.warning(None, "程序已在运行",
            "PS5 直播推流助手已经在运行了（多个实例会争抢 53/1935 端口）。\n"
            "请在系统托盘找到它。")
        sys.exit(0)

    splash = Splash()
    win = {}
    state = {"ended": False, "shown": False}

    def make_window():
        if "w" not in win:
            win["w"] = MainWindow(app)
            win["w"].setWindowOpacity(0.0)

    def reveal(w):
        if state["shown"]:
            return
        state["shown"] = True
        w.show()
        anim = QPropertyAnimation(w, b"windowOpacity", w)
        anim.setDuration(420)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.start()
        w._show_anim = anim
        if os.environ.get("PS5LIVE_SELFTEST"):
            QTimer.singleShot(5000, lambda: selftest(w))

    def finish_boot():
        """结束启动动画、进入主界面；任何异常都不允许把启动画面卡住。"""
        if state["ended"]:
            return
        state["ended"] = True
        try:
            make_window()
        except Exception as e:
            print("build main window failed:", e)
        w = win.get("w")
        if w is None:
            QTimer.singleShot(300, app.quit)
            return
        if w.isVisible():
            splash.close()
        else:
            splash.finish(lambda: reveal(w))

    def selftest(w):
        """打包自测：截图 + 探测关键路径，写标记文件后退出。"""
        import time
        try:
            root = os.path.abspath(os.path.join(os.path.dirname(core.MEDIAMTX_EXE), ".."))
            shot = os.path.join(root, "selftest_shot.png")
            w.grab().save(shot)
            # 全屏截图：确认启动画面已彻底消失，只剩主窗口
            screen_shot = os.path.join(os.path.dirname(core.BASE_DIR), "selftest_screen.png")
            app.primaryScreen().grabWindow(0).save(screen_shot)
            info = {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "frozen": bool(getattr(sys, "frozen", False)),
                "splash_closed_early": state["ended"] and state["shown"],
                "base_dir": core.BASE_DIR,
                "config_path": core.CONFIG_PATH,
                "mediamtx": core.find_mediamtx(),
                "ffmpeg": core.find_ffmpeg(),
                "ip": core.detect_gateway_ip(core.load_config().get("网关IP", "")),
                "screenshot": shot,
                "screen": screen_shot,
            }
            marker = os.path.join(os.path.dirname(core.BASE_DIR) or core.BASE_DIR,
                                  "selftest_result.txt")
            with open(marker, "w", encoding="utf-8") as f:
                for k, v in info.items():
                    f.write("%s = %s\n" % (k, v))
        except Exception as e:
            with open(os.path.join(os.path.expanduser("~"), "selftest_error.txt"), "w") as f:
                f.write(repr(e))
        finally:
            app.quit()

    steps = [
        ("正在初始化图形界面…", 0.18, 240),
        ("检测本机网卡与局域网 IP…", 0.42, 520),
        ("校准 DNS 劫持与收流端口…", 0.68, 520),
        ("加载配置，准备就绪…", 0.9, 480),
    ]

    def run_step(i):
        try:
            if i < len(steps):
                text, prog, delay = steps[i]
                splash.set_status(text, prog)
                if i == 2:
                    make_window()
                QTimer.singleShot(delay, lambda: run_step(i + 1))
            else:
                splash.set_status("准备就绪", 1.0)
                if "w" not in win:
                    make_window()
                QTimer.singleShot(300, finish_boot)
        except Exception as e:
            print("boot step error:", e)
            QTimer.singleShot(0, finish_boot)

    # 启动动画：可拖动；点击任意位置立即进入
    splash.skip_callback = lambda: QTimer.singleShot(0, finish_boot)

    splash.start()
    QTimer.singleShot(150, lambda: run_step(0))
    # 兜底：无论发生什么，8 秒后一定进入主界面，绝不让启动画面卡住
    QTimer.singleShot(8000, finish_boot)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
