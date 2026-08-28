# -*- mode: python ; coding: utf-8 -*-
"""一键版打包配置（PyInstaller）。

用法：
  pyinstaller build.spec
产物：dist/拉格朗日考勤/拉格朗日考勤.exe  （单文件夹，双击即用，完全离线）

要点：
  - 入口 attendance_gui.py（本地网页 GUI，零额外依赖）
  - 强制打包 RapidOCR 的 3 个模型 onnx（否则运行时找不到模型）
  - 隐藏导入 onnxruntime / opencv / openpyxl 等
"""
import os
import rapidocr_onnxruntime

PKG_DIR = os.path.dirname(rapidocr_onnxruntime.__file__)
MODELS_DIR = os.path.join(PKG_DIR, "models")

# RapidOCR 需要的数据文件（PyInstaller 只自动收 .py，yaml 必须显式打包）
RAPIDOCR_DATAS = [
    (MODELS_DIR, "rapidocr_onnxruntime/models"),
    (os.path.join(PKG_DIR, "config.yaml"), "rapidocr_onnxruntime"),
    (os.path.join(PKG_DIR, "ch_ppocr_v2_cls", "config.yaml"), "rapidocr_onnxruntime/ch_ppocr_v2_cls"),
    (os.path.join(PKG_DIR, "ch_ppocr_v3_det", "config.yaml"), "rapidocr_onnxruntime/ch_ppocr_v3_det"),
    (os.path.join(PKG_DIR, "ch_ppocr_v3_rec", "config.yaml"), "rapidocr_onnxruntime/ch_ppocr_v3_rec"),
]

block_cipher = None

a = Analysis(
    ["attendance_gui.py"],
    pathex=[],
    binaries=[],
    datas=RAPIDOCR_DATAS,
    hiddenimports=[
        "onnxruntime",
        "rapidocr_onnxruntime",
        "rapidocr_onnxruntime.ch_ppocr_v3_det",
        "rapidocr_onnxruntime.ch_ppocr_v3_rec",
        "rapidocr_onnxruntime.ch_ppocr_v2_cls",
        "cv2",
        "numpy",
        "openpyxl",
        "PIL",
        "pkg_resources",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6"],
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
