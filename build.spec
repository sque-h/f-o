# -*- mode: python ; coding: utf-8 -*-
"""打包配置（PyInstaller，可选）。

不打包也能用——直接 `python attendance_gui.py` 即可。
想把源码做成双击即用的单文件夹 exe（自己留用/发给队友），才需要这个：

用法：
  pyinstaller build.spec
产物：dist/拉格朗日考勤/拉格朗日考勤.exe  （单文件夹，完全离线）

要点：
  - 入口 attendance_gui.py（本地网页 GUI，零额外依赖）
  - 本地 OCR 引擎为 PP-OCRv6 (medium)，模型在 ocr_models_v6/ 目录，需显式打包
  - 隐藏导入 onnxruntime / opencv / openpyxl 等
"""
import os

# v6 本地模型目录（与 build.spec 同级；SPECPATH 由 PyInstaller 注入）
MODELS_DIR = os.path.join(SPECPATH, "ocr_models_v6")

V6_DATAS = [
    (MODELS_DIR, "ocr_models_v6"),
]

block_cipher = None

a = Analysis(
    ["attendance_gui.py"],
    pathex=[],
    binaries=[],
    datas=V6_DATAS,
    hiddenimports=[
        "onnxruntime",
        "cv2",
        "numpy",
        "openpyxl",
        "PIL",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6", "rapidocr_onnxruntime"],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="拉格朗日考勤",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,          # 不弹黑窗口
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="拉格朗日考勤",
)
