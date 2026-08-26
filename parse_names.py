#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 OCR 结果提取玩家名（考勤1.0 名字纠错核心，开源复用）。

单格式：纯名字考勤截图（纵向排列玩家名，无数字列）。
逻辑：左侧名字区筛选 → 长度/噪声过滤 → 形近字纠正 → 比名册。
"""
import re
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


# ---- 截图类型识别（决定 recognize 走哪条提取路径）----
# 移植自完整版 classify_screenshot.py，适配 RapidOCR 输出的 {text,x,y} 中心坐标。
MEMBER_HEADERS = {"玩家名", "繁荣度", "周活跃度", "身份", "小队名称", "队伍类型", "小队"}
COORD_RE = re.compile(r"坐标|\(\d{3,},\s*\d{3,}\)|\d{4,},\s*\d{4,}")
FLEET_RE = re.compile(r"\d+号舰队|[一二三四五六七八九十百千]+号舰队")


def classify(items):
    """根据 OCR 文本块判断截图类型。items 为 ocr_local.ocr_image 输出。
    返回 member_list / attendance_list / starmap / unknown。
    """
    texts = [(it.get("text", "").strip(), it.get("x", 0), it.get("y", 0))
             for it in items if it.get("text")]
    if not texts:
        return "unknown"

    headers_found = set()
    for t, _, _ in texts:
        for h in MEMBER_HEADERS:
            if h in t:
                headers_found.add(h)
    header_score = len(headers_found)

    num_pat = re.compile(r"^\d+(\.\d+)?万?$")
    right_numbers = sum(
        1 for t, xc, _ in texts
        if xc >= 600 and num_pat.match(t.replace(",", "").replace("，", ""))
    )
    coord_hits = sum(1 for t, _, _ in texts if COORD_RE.search(t))
    fleet_hits = sum(1 for t, _, _ in texts if FLEET_RE.search(t))

    name_like = 0
    for t, _, _ in texts:
        if 2 <= len(t) <= 12 and not t.isdigit() and t not in NOISE:
            name_like += 1

    if header_score >= 2 or right_numbers >= 5:
        return "member_list"
    if fleet_hits >= 2 or coord_hits >= 2:
        return "starmap"
    if name_like >= 5 and right_numbers == 0 and header_score == 0:
        return "attendance_list"
    return "unknown"


def extract_names_starmap(items, known, min_match=0.75):
    """从集合点星图（图片）提取到场玩家名。

    星图比纯名字截图噪：含坐标、舰队编号、星球/星系名等 UI 文字。
    策略：过滤坐标/舰队/数值噪声 → 其余名字类文本与名册模糊匹配 → 命中即到场。
    不限制 x 范围（星图名字分布在全图），靠名册匹配兜住误报。
    返回 [(name, raw, score, status)]，与 extract_names 同构，可直接喂考勤流程。
    """
    candidates = []
    for it in items:
        t = apply_char_fix(it["text"]).strip()
        if not (2 <= len(t) <= 12):
            continue
        if t.isdigit() or t in NOISE:
            continue
        if COORD_RE.search(t) or FLEET_RE.search(t):
            continue
        if _looks_like_number(t):
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


# 身份列词（成员列表截图里紧跟名字右侧，但不是小队，提取名册时排除）
IDENTITY = {"指挥官", "精英", "成员", "学员", "新兵", "管理者", "盟主", "副盟主",
            "军官", "领袖", "官员", "外交官", "政委", "参谋", "干事", "长老"}

# 像繁荣度/周活跃度的数值文本（含「万」、含小数点、纯数字），提取名册时排除
_NUMISH = re.compile(r"万|\d\.\d|\d+(\.\d+)?\s*万?")


def _looks_like_number(t):
    if t.isdigit():
        return True
    return bool(_NUMISH.search(t))


def extract_roster(items, name_x_max=650, y_tol=25):
    """从全盟截图一键提取名册（玩家名 + 小队）。

    兼容两种截图，无需分支：
      - 成员列表截图（含「玩家名 + 小队名称」列）→ 名字在左列，小队在同行右侧
      - 纯名字截图（无小队列）→ 右侧无文本，小队留空
    返回 [(name, team), ...]，team 为空表示截图里没有小队信息。
    """
    name_cands = []
    for it in items:
        t = apply_char_fix(it["text"]).strip()
        if not (2 <= len(t) <= 12):
            continue
        if it["x"] > name_x_max:
            continue
        if t.isdigit() or t in NOISE:
            continue
        name_cands.append((it["y"], it["x"], t))
    name_cands.sort()

    seen = set()
    raw = []
    for y, x, t in name_cands:
        if t in seen:
            continue
        seen.add(t)
        team = ""
        best_dx = 10 ** 9
        for it in items:
            ti = apply_char_fix(it["text"]).strip()
            if ti.isdigit() or ti in NOISE or ti in IDENTITY or _looks_like_number(ti):
                continue
            if abs(it["y"] - y) > y_tol:
                continue
            if it["x"] <= x:
                continue
            dx = it["x"] - x
            if dx < best_dx and 1 <= len(ti) <= 8:
                best_dx = dx
                team = ti
        raw.append((t, team))

    # 第二遍：剔除「小队标题行」。成员列表截图里小队名常作为分组标题独占一行，
    # 同时它又是其成员的 team 值。收集所有 team → 已知小队名集，name 命中即剔除。
    known_teams = {tm for _, tm in raw if tm}
    roster = [(n, tm) for n, tm in raw if n not in known_teams]
    return roster
