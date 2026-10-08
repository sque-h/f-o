#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 OCR 结果提取玩家名（考勤1.0 名字纠错核心，开源复用）。

单格式：纯名字考勤截图（纵向排列玩家名，无数字列）。
逻辑：左侧名字区筛选 → 长度/噪声过滤 → 形近字纠正 → 比名册。
"""
import re
from difflib import SequenceMatcher

# 逐字纠正（OCR 把单字读成形近/同音字）。
# 这里只留通用噪声：竖线常被 OCR 误认成一个汉字，直接去掉。
# 想针对你自己的名册纠错，按 {"错字": "正字"} 往下加即可。
CHAR_FIX = {
    "丨": "", "|": "",
}
# 整词纠正：OCR 把整个词读成另一种写法时，直接映射回名册里的正确名。
# 留空不影响使用；需要时照下面格式填你自己的：
#     "OCR 读出来的错名": "名册里的正确名",
FIX_MAP = {
}

NOISE = {
    "成员", "队长", "副队长", "玩家名", "繁荣度", "周活跃度", "身份",
    "小队名称", "队伍类型", "A1", "A2", "A3", "A4", "A5", "A6", "A7",
}


def apply_char_fix(text):
    return "".join(CHAR_FIX.get(ch, ch) for ch in text)


_NORM_KEY_RE = re.compile(r"[^\w\u4e00-\u9fff]")


def _norm_key(s):
    """只留字母数字和汉字，用来判断「原文是不是已经能对上名册」。"""
    return _NORM_KEY_RE.sub("", str(s).strip().lower())


def raw_hits_roster(raw, known):
    """原文本身就能对上名册（精确命中，或已含某个完整名）→ 不必再做形近字纠正。

    这样既能保住全大写 ID、带数字 ID 这类真名，又不影响真正读错字时的纠正。
    """
    t = str(raw).strip()
    if not t:
        return False
    if t in known:
        return True
    nt = _norm_key(t)
    if not nt:
        return False
    return any(len(nk) >= 2 and nk in nt for nk in (_norm_key(k) for k in known))


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
    merged = _merge_wrapped(items, name_x_max)
    candidates = [(y, t) for y, x, t in merged]
    candidates.sort()
    seen = set()
    results = []
    for yc, t in candidates:
        if t in seen:
            continue
        seen.add(t)
        if FIX_MAP.get(t):
            t = FIX_MAP[t]
        name, score = best_match(t, known)
        if score >= min_match:
            results.append((name, t, round(score, 2), "ok"))
        elif score >= min_match - 0.15:
            results.append((name or t, t, round(score, 2), "guess"))
    return results


# ---- 截图类型识别（决定 recognize 走哪条提取路径）----
# 移植自完整版 classify_screenshot.py，适配本地 PP-OCRv6 输出的 {text,x,y} 中心坐标。
MEMBER_HEADERS = {"玩家名", "繁荣度", "周活跃度", "身份", "小队名称", "队伍类型", "小队"}
COORD_RE = re.compile(r"坐标|\(\d{3,},\s*\d{3,}\)|\d{4,},\s*\d{4,}")
FLEET_RE = re.compile(r"\d+号舰队|[一二三四五六七八九十百千]+号舰队")
# 建造/资源类界面文字：整段是 UI 时不能拿去比对名册，
# 否则「建造计划(1D)」这种会被名册里的短名「1D」误命中（误报为到场）。
UI_TEXT_RE = re.compile(
    r"建造|计划|前哨站|队列|解构|晶体|金属|重氢|采矿|采集|研究|升级|"
    r"资源|坐标|支援|集结|筛选|篩选|行动目标|倒计时|完成度"
)
# 「7/10」「7/1D」这类进度/数量写法（建造队列、资源进度），不是名字
PROGRESS_RE = re.compile(r"^[0-9A-Za-z. ]{1,4}/[0-9A-Za-z. ]{1,8}$")


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
        orig = str(it["text"]).strip()
        if orig.isdigit() or _looks_like_number(orig) or _is_prosperity_like(orig):
            continue
        if PROGRESS_RE.match(orig) or COORD_RE.search(orig):
            continue
        t = orig if raw_hits_roster(orig, known) else apply_char_fix(orig).strip()
        if len(t) < 1 or len(t) > 12:
            continue
        if len(t) == 1 and (not _CJK.match(t) or t in SINGLE_NOISE):
            continue
        if t.isdigit() or t in NOISE:
            continue
        if COORD_RE.search(t) or FLEET_RE.search(t):
            continue
        if UI_TEXT_RE.search(t):
            continue
        if PROGRESS_RE.match(t):
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


def extract_names_owner_labels(items, known, min_match=0.75):
    """新版星图（舰队所属人名）提取。

    2026-09 游戏更新后，星图会直接把舰队所有者名字标在舰队旁边；
    名字可能互相重叠成一段长文本（两个名字挤在一起，中间没有任何分隔）。
    策略：
      1) OCR 文本先去掉坐标/舰队编号/繁荣度等 UI 噪声；
      2) 若一段文本里包含名册全名，按包含关系拆出人名；
         同一段里长名包含短名时只保留长名（避免把长名的一截误算成另一个人）；
      3) 没有包含命中时再用相似度匹配。
    返回 [(name, raw, score, status)]，与 extract_names 同构。
    """
    seen = set()
    results = []

    def norm(s):
        return re.sub(r"[^\w\u4e00-\u9fff]", "", str(s).strip().lower())

    known_norm = [(k, norm(k)) for k in known if norm(k)]
    for it in items:
        orig = str(it.get("text", "")).strip()
        # 先用「原始 OCR 文本」判数字/进度类界面文字：形近字纠正会把 0/O 读成 D，
        # 纠正之后再判就认不出来了（例：「1030」会被纠成「1D3D」，进而命中名册里的短名）
        if orig.isdigit() or _looks_like_number(orig) or _is_prosperity_like(orig):
            continue
        if PROGRESS_RE.match(orig) or COORD_RE.search(orig):
            continue
        raw = orig if raw_hits_roster(orig, known) else apply_char_fix(orig).strip()
        if not raw or len(raw) > 30:
            continue
        if raw in NOISE or raw.isdigit() or _looks_like_number(raw) or _is_prosperity_like(raw):
            continue
        if COORD_RE.search(raw) or FLEET_RE.search(raw):
            continue
        if UI_TEXT_RE.search(raw):
            continue
        if PROGRESS_RE.match(raw):
            continue
        if FIX_MAP.get(raw):
            raw = FIX_MAP[raw]
        nr = norm(raw)
        if not nr:
            continue

        # 只有大小写不同的同一个 ID 优先精确命中，避免都算上
        if raw in known:
            if raw not in seen:
                seen.add(raw)
                results.append((raw, raw, 1.0, "ok"))
            continue

        subs = []
        for k, nk in known_norm:
            if len(nk) >= 2 and nk in nr:
                subs.append((k, len(nk)))
        if subs:
            max_len = max(ln for _k, ln in subs)
            for k, ln in subs:
                if k in seen:
                    continue
                # 长名包含短名时，丢弃短名（如 希灵灰烬 vs 希灵）
                if ln < max_len and any(ln < oln and norm(k) in norm(ok) for ok, oln in subs):
                    continue
                seen.add(k)
                results.append((k, raw, 1.0, "ok"))
            continue

        name, score = best_match(raw, known)
        if score >= min_match:
            if name not in seen:
                seen.add(name)
                results.append((name, raw, round(score, 2), "ok"))
        elif score >= min_match - 0.15:
            if name not in seen:
                seen.add(name)
                results.append((name or raw, raw, round(score, 2), "guess"))
    return results


# 身份列词（成员列表截图里紧跟名字右侧，但不是小队，提取名册时排除）
IDENTITY = {"指挥官", "精英", "成员", "学员", "新兵", "管理者", "盟主", "副盟主",
            "军官", "领袖", "官员", "外交官", "政委", "参谋", "干事", "长老"}

# 像繁荣度/周活跃度的数值文本（含「万」、含小数点、纯数字），提取名册时排除。
# 用 fullmatch 锚定：整串都是数值才判为数值，避免误杀带数字的真名字（如「开拓者595117」）。
_NUMISH = re.compile(r"^[\d,]+(\.\d+)?\s*万?$")


def _looks_like_number(t):
    if t.isdigit():
        return True
    return bool(_NUMISH.fullmatch(t))


# 繁荣度数值的特征：整串是数值，或含有「万」（游戏里繁荣度恒带「万」，玩家名几乎不含）。
def _is_prosperity_like(t):
    if "万" in t:
        return True
    return _looks_like_number(t)


# ---- 小队名识别增强（小队名含数字时易误读，如「6队」被读成「b队」）----
# 内置只放通用「N队」；你自己名册里的小队名会被自动读进来（见 _load_squad_vocab）。
SQUAD_VOCAB = ["一队", "二队", "三队", "四队", "五队", "七队", "八队",
               "九队", "十队", "6队"]
# 阿拉伯/中文数字互转（六→6，陆→6）
CN_NUM = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5", "六": "6",
          "陆": "6", "七": "7", "八": "8", "九": "9", "十": "10"}
# OCR 把数字读成形近字母的常见混淆
DIGIT_CONFUSE = {"b": "6", "B": "8", "o": "0", "O": "0", "l": "1", "I": "1",
                 "S": "5", "Z": "2", "q": "9", "g": "9", "t": "1"}


def _norm_squad_text(t):
    t = t.strip()
    out = []
    for ch in t:
        out.append(DIGIT_CONFUSE.get(ch, ch))
    t = "".join(out)
    for k, v in CN_NUM.items():
        t = t.replace(k, v)
    return t.replace(" ", "")


def _load_squad_vocab():
    """小队名词表 = 内置常见 + 用户已建名册里的真实小队名（更准）。
    名册里的小队名也做数字归一（六队→6队），保证与内置词表口径一致。
    """
    vocab = list(SQUAD_VOCAB)
    try:
        import csv
        with open("roster.csv", encoding="utf-8-sig", newline="") as fh:
            for row in csv.reader(fh):
                if len(row) >= 3 and row[2].strip():
                    vocab.append(_norm_squad_text(row[2].strip()))
    except OSError:
        pass
    return list(dict.fromkeys(vocab))


def normalize_squad(tok, vocab):
    """把 OCR 出的小队名归一化到词表。命中即返回规范名；否则保留原样。"""
    if not tok:
        return ""
    if tok in vocab:
        return tok
    t = _norm_squad_text(tok)
    if t in vocab:
        return t
    # 词表本身也按归一化形式比对（六队/6队 视为同一）
    norm_vocab = {_norm_squad_text(v): v for v in vocab}
    if t in norm_vocab:
        return norm_vocab[t]
    best, score = "", 0.0
    for nv, v in norm_vocab.items():
        s = SequenceMatcher(None, t, nv).ratio()
        if s > score:
            best, score = v, s
    return best if score >= 0.5 else tok


# 单字白名单外的 UI 杂字（出现在名字列但不是名字）
SINGLE_NOISE = {"队", "盟", "名", "列", "小", "大", "中", "长", "玩", "家",
                "身", "份", "繁", "荣", "度", "周", "活", "跃", "类", "型",
                "本", "页", "上", "下", "左", "右", "全", "员"}
_CJK = re.compile(r"^[\u4e00-\u9fff]+$")


def _is_name_fragment(t):
    """该文本是否可能作为「名字片段」参与竖屏换行合并 / 候选。"""
    if not t:
        return False
    if t.isdigit() or t in NOISE or _is_prosperity_like(t):
        return False
    if len(t) > 12:
        return False
    if len(t) == 1 and (not _CJK.match(t) or t in SINGLE_NOISE):
        return False
    return True


def _merge_wrapped(items, name_x_max):
    """合并名字列内因竖屏换行被拆成两行的玩家名。

    竖屏（或窄列）截图里一个玩家名可能折成两行 OCR 文本；二者同在名字列、
    纵向相邻、第二片段较短。合并后还原真名，避免被当成两个名字。
    返回按 y 排序的 [(y, x, text)]。
    """
    frags = []
    for it in items:
        t = apply_char_fix(it["text"]).strip()
        if it["x"] > name_x_max:
            continue
        if not _is_name_fragment(t):
            continue
        frags.append((it["y"], it["x"], t))
    frags.sort()
    if len(frags) < 2:
        return frags
    ys = [f[0] for f in frags]
    gaps = sorted(ys[i + 1] - ys[i] for i in range(len(ys) - 1) if ys[i + 1] - ys[i] > 0)
    med_gap = gaps[len(gaps) // 2] if gaps else 30
    merged, i = [], 0
    while i < len(frags):
        y, x, t = frags[i]
        if i + 1 < len(frags):
            y2, x2, t2 = frags[i + 1]
            dy = y2 - y
            if (dy > 0 and dy < 0.75 * med_gap and abs(x2 - x) < 40
                    and len(t2) <= 8 and len(t) + len(t2) <= 12):
                merged.append((y, min(x, x2), t + t2))
                i += 2
                continue
        merged.append((y, x, t))
        i += 1
    return merged


def extract_roster(items, name_x_max=650, y_tol=25, squad_vocab=None):
    """从全盟截图一键提取名册（玩家名 + 小队）。

    兼容两种截图，无需分支：
      - 成员列表截图（含「玩家名 + 小队名称」列）→ 名字在左列，小队在同行右侧
      - 纯名字截图（无小队列）→ 右侧无文本，小队留空
    返回 [(name, team), ...]，team 为空表示截图里没有小队信息。
    """
    if squad_vocab is None:
        squad_vocab = _load_squad_vocab()
    merged = _merge_wrapped(items, name_x_max)
    seen = set()
    raw = []
    for y, x, t in merged:
        if t in seen:
            continue
        seen.add(t)
        team = ""
        best_dx = 10 ** 9
        for it in items:
            ti = apply_char_fix(it["text"]).strip()
            if ti.isdigit() or ti in NOISE or ti in IDENTITY or _is_prosperity_like(ti):
                continue
            if abs(it["y"] - y) > y_tol:
                continue
            if it["x"] <= x:
                continue
            dx = it["x"] - x
            if dx < best_dx and 1 <= len(ti) <= 8:
                best_dx = dx
                team = ti
        team = normalize_squad(team, squad_vocab) if team else ""
        # 单字名若截图上没有小队（纯名字截图/UI杂字）则丢弃，避免污染名册
        if len(t) == 1 and not team:
            continue
        raw.append((t, team))

    # 第二遍：剔除「小队标题行」。成员列表截图里小队名常作为分组标题独占一行，
    # 同时它又是其成员的 team 值。收集所有 team → 已知小队名集，name 命中即剔除。
    known_teams = {tm for _, tm in raw if tm}
    roster = [(n, tm) for n, tm in raw if n not in known_teams]
    return roster
