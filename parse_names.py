#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 OCR 结果提取玩家名（考勤1.0 名字纠错核心，开源复用）。

单格式：纯名字考勤截图（纵向排列玩家名，无数字列）。
逻辑：左侧名字区筛选 → 长度/噪声过滤 → 形近字纠正 → 比名册。
"""
from difflib import SequenceMatcher

# 逐字纠正（OCR 把单字读成形近/同音字）
CHAR_FIX = {
    "焓": "晗", "I": "", "丨": "", "|": "",
    "盔": "盈", "壮": "社", "擎": "攀",
    "星": "心", "王": "主", "寞": "冥",
    "O": "D", "o": "d", "0": "D",
}
# 整词纠正（OCR 把整词读成另一个常见错误形式时，直接映射回名册名）
FIX_MAP = {
    "希灵I清风": "希灵清风",
    "许盔": "许盈",
    "粗口壮熊福瑞": "粗口社熊福瑞",
    "超擎": "超攀",
    "策星无畏": "策心无畏",
    "神豆国王": "神豆国主",
    "开拓者715624": "开拓者574162",
    "幽寞冥神王幽冥神王": "幽冥神王",
    "旧日愚者旧日患者": "旧日愚者",
    "灯火阑珊口灯火阑珊": "灯火阑珊o",
}

NOISE = {
    "成员", "队长", "副队长", "玩家名", "繁荣度", "周活跃度", "身份",
    "小队名称", "队伍类型", "A1", "A2", "A3", "A4", "A5", "A6", "A7",
}


def apply_char_fix(text):
    return "".join(CHAR_FIX.get(ch, ch) for ch in text)


def best_match(name, known):
    best, score = "", 0.0
    for k in known:
        s = SequenceMatcher(None, name, k).ratio()
        if s > score:
            best, score = k, s
    return best, score


def extract_names(items, known, name_x_max=650, min_match=0.75):
    """items: ocr_local.ocr_image 输出。known: 名册名列表。
    返回 [(name, raw, score, status)]，status ∈ {ok, guess}。
    """
    candidates = []
    for it in items:
        t = apply_char_fix(it["text"]).strip()
        if not (2 <= len(t) <= 12):
            continue
        if it["x"] > name_x_max:
            continue
        if t.isdigit() or t in NOISE:
            continue
        if FIX_MAP.get(t):
            t = FIX_MAP[t]
        candidates.append((it["y"], t))

    candidates.sort(key=lambda p: p[0])
    seen = set()
    results = []
    for yc, t in candidates:
        if t in seen:
            continue
        seen.add(t)
        name, score = best_match(t, known)
        if score >= min_match:
            results.append((name, t, round(score, 2), "ok"))
        elif score >= min_match - 0.15:
            results.append((name or t, t, round(score, 2), "guess"))
    return results
