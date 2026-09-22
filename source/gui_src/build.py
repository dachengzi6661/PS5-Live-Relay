# -*- coding: utf-8 -*-
"""打包入口：生成图标/启动图 → PyInstaller 单文件 → 复制到工具根目录。"""
import os
import sys
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_ROOT = os.path.dirname(HERE)
APP_NAME = "PS5直播推流助手"


def main():
    # 1) 资源
    subprocess.run([sys.executable, os.path.join(HERE, "make_assets.py")], check=True)

    # 2) PyInstaller
    excludes = [
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
        "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.Qt3DCore",
        "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DLogic",
        "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQml", "PySide6.QtQmlModels",
        "PySide6.QtQuickWidgets", "PySide6.QtQuickControls2", "PySide6.QtCharts",
        "PySide6.QtDataVisualization", "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
        "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtBluetooth",
        "PySide6.QtNfc", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtXml",
        "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtSerialPort",
        "PySide6.QtSensors", "PySide6.QtSvgWidgets",
        "tkinter", "unittest", "pydoc", "test",
    ]
    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile",
        "--windowed", "--uac-admin",
        "--name", APP_NAME,
        "--icon", os.path.join("assets", "app.ico"),
        "--splash", os.path.join("assets", "splash.png"),
        "--add-data", "assets" + os.pathsep + "assets",
        "--collect-submodules", "dnslib",
    ]
    for m in excludes:
        cmd += ["--exclude-module", m]
    cmd.append(os.path.join(HERE, "app.py"))

    print(">> 打包中…")
    subprocess.run(cmd, cwd=HERE, check=True)

    # 3) 复制到工具根目录
    src = os.path.join(HERE, "dist", APP_NAME + ".exe")
    dst = os.path.join(TOOL_ROOT, APP_NAME + ".exe")
    shutil.copy2(src, dst)
    size_mb = os.path.getsize(dst) / 1024 / 1024
    print("✅ 打包完成：%s（%.1f MB）" % (dst, size_mb))


if __name__ == "__main__":
    main()
