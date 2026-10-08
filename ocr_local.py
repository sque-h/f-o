#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地 OCR 封装（PP-OCRv6 medium，零密钥、纯离线）。

本地 PP-OCRv6 (medium) 推理引擎，替代旧的 RapidOCR(PP-OCRv3)，名字/数字识别更强、置信度更高。
输入图片路径，输出文本块列表（与旧接口完全一致）：
  [{"text":..., "score":..., "x":中心x, "y":中心y}, ...]

模型目录：本文件同级 ocr_models_v6/（PP-OCRv6_medium_det.onnx / _rec.onnx / ppocrv6_dict.txt）。
PyInstaller 冻结后自动改为 sys._MEIPASS/ocr_models_v6。
"""
import os
import sys
import math
import numpy as np
import cv2
from PIL import Image

try:
    import onnxruntime as ort
except ImportError:
    ort = None


def _model_dir():
    base = sys._MEIPASS if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "ocr_models_v6")


_MEAN = [0.485, 0.456, 0.406]
_STD = [0.229, 0.224, 0.225]


def _to_bgr(img):
    if img is None:
        return None
    if img.ndim == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.ndim == 3:
        c = img.shape[2]
        if c == 4:
            return cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        if c == 3:
            return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    return img


class V6Reader:
    def __init__(self, model_dir=None):
        if ort is None:
            raise RuntimeError("未安装 onnxruntime，请先：pip install onnxruntime")
        md = model_dir or _model_dir()
        det_p = os.path.join(md, "PP-OCRv6_medium_det.onnx")
        rec_p = os.path.join(md, "PP-OCRv6_medium_rec.onnx")
        dict_p = os.path.join(md, "ppocrv6_dict.txt")
        for f in (det_p, rec_p, dict_p):
            if not os.path.exists(f):
                raise FileNotFoundError(f"缺少模型文件：{f}（期望目录 {md}）")
        so = ort.SessionOptions()
        so.intra_op_num_threads = 4
        self.det = ort.InferenceSession(det_p, providers=["CPUExecutionProvider"], sess_options=so)
        self.rec = ort.InferenceSession(rec_p, providers=["CPUExecutionProvider"], sess_options=so)
        with open(dict_p, encoding="utf-8") as f:
            self.char_list = [l.rstrip("\n") for l in f]
        self._det_preprocess(np.zeros((320, 320, 3), np.uint8))

    def _det_preprocess(self, img, limit=960, limit_type="min"):
        h, w = img.shape[:2]
        if limit_type == "min":
            scale = limit / min(h, w) if min(h, w) > limit else 1.0
        else:
            scale = limit / max(h, w) if max(h, w) > limit else 1.0
        rh = int(round(h * scale))
        rw = int(round(w * scale))
        img = cv2.resize(img, (rw, rh))
        maxh = int(math.ceil(rh / 32.0) * 32)
        maxw = int(math.ceil(rw / 32.0) * 32)
        padded = np.zeros((maxh, maxw, 3), dtype=np.float32)
        padded[:rh, :rw] = img.astype(np.float32)
        padded = padded / 255.0
        for i in range(3):
            padded[:, :, i] = (padded[:, :, i] - _MEAN[i]) / _STD[i]
        blob = padded.transpose(2, 0, 1)[None].astype(np.float32)
        return blob, (h, w, rh, rw)

    @staticmethod
    def _unclip(box, ratio):
        cx = box[:, 0].mean()
        cy = box[:, 1].mean()
        out = []
        for x, y in box:
            out.append([cx + (x - cx) * ratio, cy + (y - cy) * ratio])
        return np.array(out, np.float32)

    def _det_postprocess(self, pred, meta):
        oh, ow, rh, rw = meta
        prob = pred[0, 0]
        binary = (prob > 0.3).astype(np.uint8)
        contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        boxes, scores = [], []
        sx, sy = ow / float(rw), oh / float(rh)
        for c in contours:
            if cv2.contourArea(c) < 4:
                continue
            mask = np.zeros_like(binary)
            cv2.drawContours(mask, [c], -1, 1, -1)
            score = (prob * mask).sum() / max(mask.sum(), 1)
            if score < 0.6:
                continue
            rect = cv2.minAreaRect(c)
            pts = cv2.boxPoints(rect)
            pts = self._unclip(pts, 1.6)
            pts = np.clip(pts, 0, None)
            xmin, ymin = pts[:, 0].min(), pts[:, 1].min()
            xmax, ymax = pts[:, 0].max(), pts[:, 1].max()
            boxes.append([int(round(xmin * sx)), int(round(ymin * sy)),
                          int(round(xmax * sx)), int(round(ymax * sy))])
            scores.append(float(score))
        return boxes, scores

    def _rec_preprocess(self, crop, rec_h=48, rec_w=320):
        h, w = crop.shape[:2]
        ratio = w / float(h)
        rw = int(round(rec_h * ratio))
        if rw > rec_w:
            rw = rec_w
        crop = cv2.resize(crop, (rw, rec_h))
        if rw < rec_w:
            crop = np.concatenate([crop, np.zeros((rec_h, rec_w - rw, 3), np.float32)], axis=1)
        crop = crop.astype(np.float32) / 255.0
        return crop.transpose(2, 0, 1)[None].astype(np.float32)

    def _decode(self, logits):
        preds = logits.argmax(1)
        out = []
        last = -1
        for c in preds:
            c = int(c)
            if c == 0:
                last = -1
                continue
            if c == last:
                continue
            last = c
            if 1 <= c <= len(self.char_list):
                out.append(self.char_list[c - 1])
        return "".join(out)

    def ocr(self, img):
        img_bgr = _to_bgr(img)
        blob, meta = self._det_preprocess(img_bgr)
        pred = self.det.run(None, {"x": blob})[0]
        boxes, scores = self._det_postprocess(pred, meta)
        items = []
        h, w = img_bgr.shape[:2]
        for (x1, y1, x2, y2), sc in zip(boxes, scores):
            x1, y1, x2, y2 = max(0, x1 - 2), max(0, y1 - 2), min(w, x2 + 2), min(h, y2 + 2)
            crop = img_bgr[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            rb = self._rec_preprocess(crop)
            logits = self.rec.run(None, {"x": rb})[0][0]
            text = self._decode(logits)
            if not text.strip():
                continue
            items.append({"text": text, "score": sc, "x": (x1 + x2) / 2, "y": (y1 + y2) / 2,
                          "x1": x1, "y1": y1, "x2": x2, "y2": y2})
        items.sort(key=lambda it: (round(it["y"] / 20), it["x"]))
        return items


_engine = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = V6Reader()
    return _engine


def ocr_image(path):
    # 用 Pillow 读图（支持中文路径），转 BGR numpy 数组后交给 V6Reader，
    # 避免 cv2.imread 在中文路径/文件名下读图失败。
    img = Image.open(path).convert("RGB")
    arr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    return get_engine().ocr(arr)
