#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地 OCR 封装（RapidOCR，零密钥、纯离线）。

来自考勤1.0 本地识别引擎。输入图片路径，输出文本块列表：
  [{"text":..., "score":..., "x":中心x, "y":中心y}, ...]
"""
import cv2

try:
    from rapidocr_onnxruntime import RapidOCR
except ImportError:
    RapidOCR = None

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        if RapidOCR is None:
            raise RuntimeError(
                "未安装 rapidocr-onnxruntime，请先：pip install -r requirements.txt"
            )
        _engine = RapidOCR()
    return _engine


def ocr_image(path):
    img = cv2.imread(path)
    if img is None:
        raise FileNotFoundError(f"无法读取图片：{path}")
    result, _ = get_engine()(img)
    items = []
    for box, text, score in (result or []):
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        items.append({
            "text": (text or "").strip(),
            "score": float(score) if score is not None else 0.0,
            "x": (min(xs) + max(xs)) / 2,
            "y": (min(ys) + max(ys)) / 2,
        })
    return items
