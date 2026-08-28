#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拉格朗日考勤 · 开源版 主入口。

功能：
  - 纯本地 OCR 识别名字（RapidOCR，零密钥）
  - 单格式：活动考勤截图（谁来了谁没来）——支持纯名字名单图 与 集合点星图图片（自动判断）
  - 输出 CSV + 一张本地表（xlsx）
  - 案例库自动累积（cases/），可导出样本与他人共享

用法：
  python attendance.py recognize <截图.png> [--roster roster.csv] [--type auto|starmap|attendance_list] [--date 2026-08-26]
  python attendance.py build-roster <全盟截图1.png> [全盟截图2.png ...]
  python attendance.py cases --stats
  python attendance.py cases --export [out.zip]
"""
import argparse
import csv
from collections import OrderedDict
import json
import zipfile
from datetime import datetime
from pathlib import Path

import ocr_local
import parse_names as pn

ROOT = Path(__file__).resolve().parent
ROSTER = ROOT / "roster.csv"
CASES_DIR = ROOT / "cases"
CASES_DB = CASES_DIR / "cases.jsonl"

# 历史考勤（每次 recognize 自动累积，用于统计连续/累计缺席）
HISTORY_DIR = ROOT / "history"
HISTORY_CSV = HISTORY_DIR / "attendance.csv"

# 清退阈值（与完整版一致）：连续缺席≥3次 或 赛季累计缺席≥8次（累计非连续）
CONSEC_KICK = 3
SEASON_ABSENT_CAP = 8


def load_roster(path):
    names, squads = [], {}
    if path.exists():
        with open(path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                n = (row.get("玩家名") or "").strip()
                if n:
                    names.append(n)
                    squads[n] = (row.get("小队") or "").strip()
    return names, squads


# ---------------------------------------------------------------------------
# 历史考勤：每次 recognize 累积为「活动日期,玩家名,状态」，用于统计连续/累计缺席
# ---------------------------------------------------------------------------
def load_history():
    """读取历史考勤。返回 (att, first_seen)：
        att       : {日期: set(到场玩家名)}
        first_seen: {玩家名: 首次出现的日期} —— 用于「中途入盟不算缺勤」
    """
    present = OrderedDict()
    first_seen = {}
    if HISTORY_CSV.exists():
        with open(HISTORY_CSV, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                d = (row.get("活动日期") or "").strip()
                n = (row.get("玩家名") or "").strip()
                s = (row.get("状态") or "").strip()
                if not d or not n:
                    continue
                # 确保该日期在 att 中（即使当天无人到场，也要计入缺席统计）
                present.setdefault(d, set())
                if s == "到场":
                    present[d].add(n)
                if n not in first_seen:
                    first_seen[n] = d
    return present, first_seen


def save_history(date_str, present, known):
    """把本次全名册状态追加写入 history/attendance.csv（同日期同名不重复写）。"""
    HISTORY_DIR.mkdir(exist_ok=True)
    rows = [(date_str, n, "到场" if n in present else "未到场") for n in known]
    existing = set()
    if HISTORY_CSV.exists():
        with open(HISTORY_CSV, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                existing.add((row.get("活动日期"), row.get("玩家名")))
    with open(HISTORY_CSV, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        if HISTORY_CSV.stat().st_size == 0:
            w.writerow(["活动日期", "玩家名", "状态"])
        for d, n, s in rows:
            if (d, n) not in existing:
                w.writerow([d, n, s])


def compute_absence(known, att, dates, first_seen):
    """计算每个名册成员的 (最大连续缺席段, 赛季累计缺席)。
       中途入盟：成员首次出现日期之前的场次不计入缺勤（视为尚未入盟）。
       从未在历史上出现者视为入盟晚于所有活动，全部不计入缺勤。
    """
    out = {}
    for name in known:
        join = first_seen.get(name)
        if join is None:
            out[name] = (0, 0)
            continue
        consec = 0
        max_run = 0
        cumul = 0
        for d in dates:
            if d < join:
                continue
            if name in att.get(d, set()):
                consec = 0
            else:
                consec += 1
                cumul += 1
                if consec > max_run:
                    max_run = consec
        out[name] = (max_run, cumul)
    return out


def kick_reason(name, abs_info):
    """返回该成员触发的清退原因字符串（空串=不触发）。"""
    consec, cumul = abs_info.get(name, (0, 0))
    if consec >= CONSEC_KICK:
        return f"连续缺席{consec}次"
    if cumul >= SEASON_ABSENT_CAP:
        return f"赛季累计缺席{cumul}次"
    return ""


def cmd_build_roster(args):
    roster = []
    for img in args.images:
        items = ocr_local.ocr_image(img)
        roster += pn.extract_roster(items, name_x_max=args.name_x_max)
    # 本次多张截图合并：按名字去重（保留首次出现），名单长分多张截自动拼
    seen, merged = set(), []
    for name, team in roster:
        if name in seen:
            continue
        seen.add(name)
        merged.append((name, team))
    roster = merged
    out = Path(args.out)
    # 与已有名册合并（默认追加，不覆盖）：分多次传图 / 反复生成也不会丢人
    if getattr(args, "merge", True) and out.exists():
        old_names, old_teams = load_roster(out)
        old = {n: old_teams.get(n, "") for n in old_names}
        added = 0
        for name in old_names:
            if name not in seen:
                seen.add(name)
                merged.append((name, old[name]))
                added += 1
        if added:
            print(f"  [合并] 已从已有名册保留 {added} 人（本次新增/更新 {len(roster) - added} 人）")
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["玩家名", "小队"])
        for name, team in roster:
            w.writerow([name, team])
    print(f"\n[名册] 已从截图生成：{out}  共 {len(roster)} 人")
    no_team = sum(1 for _, t in roster if not t)
    if no_team:
        print(f"  其中 {no_team} 人未识别到小队（纯名字截图无小队列），可手动补。")
    print("  生成后请核对一眼，再跑 recognize 考勤。名册示例：")
    for name, team in roster[:15]:
        tag = f" · {team}" if team else ""
        print(f"    {name}{tag}")
    if len(roster) > 15:
        print(f"    …（共 {len(roster)} 人，详见 {out}）")


def cmd_recognize(args):
    known, squads = load_roster(Path(args.roster))
    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    # 支持多张活动截图（集合点星图往往要截好几张才覆盖全联盟）
    images = args.images if isinstance(args.images, (list, tuple)) else [args.images]

    all_results = []          # 每张图提取出的 (name, raw, score, status) 汇总
    for idx, img in enumerate(images, 1):
        items = ocr_local.ocr_image(img)
        # 自动判断截图类型：纯名字名单 / 集合点星图（图片）/ 成员列表(应走 build-roster)
        cls = args.type if args.type and args.type != "auto" else pn.classify(items)
        if cls == "member_list":
            print(f"\n[提示] 第 {idx} 张图是「成员列表」（含繁荣度/小队列头），"
                  "已跳过；请改用 build-roster 生成名册，或换一张活动到场截图"
                  "（纯名字名单 / 集合点星图）。")
            continue
        if cls == "starmap":
            print(f"[识别] 第 {idx} 张：检测到集合点星图，按星图模式提取名字…")
            results = pn.extract_names_starmap(items, known, min_match=args.min_match)
        else:
            if cls == "attendance_list":
                print(f"[识别] 第 {idx} 张：检测到纯名字名单，按名单模式提取…")
            results = pn.extract_names(
                items, known, name_x_max=args.name_x_max, min_match=args.min_match
            )
        all_results.extend(results)
        append_case(img, items, results, date_str)

    # 多张图合并：同一玩家名取最高相似度的那条；任一图识别为「ok」即算到场
    combined = {}
    for name, raw, score, status in all_results:
        if name not in combined or score > combined[name][1]:
            combined[name] = (raw, score, status)
    results = [(n, raw, score, status) for n, (raw, score, status) in combined.items()]
    if not results:
        print("\n[考勤] 没有从截图里识别出任何到场成员（可能全是成员列表图，或名册为空）。")
        return

    present = {r[0] for r in results if r[3] == "ok"}
    absent = [n for n in known if n not in present]

    # 累积历史（默认开；--no-history 仅本次、不写入历史）
    if not args.no_history:
        save_history(date_str, present, known)

    # 基于历史计算连续/累计缺席（中途入盟：首次出现日前不计入）
    att, first_seen = load_history()
    dates = sorted(att.keys())
    abs_info = compute_absence(known, att, dates, first_seen) if dates else {}

    out_csv = ROOT / f"attendance_{date_str}.csv"
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["玩家名", "小队", "状态", "OCR文本", "相似度", "连续缺席", "累计缺席", "建议清退"])
        for name, raw, score, status in results:
            consec, cumul = abs_info.get(name, (0, 0))
            w.writerow([name, squads.get(name, ""), "到场" if status == "ok" else "疑似", raw, score,
                        consec, cumul, "是" if kick_reason(name, abs_info) else ""])
        for n in absent:
            consec, cumul = abs_info.get(n, (0, 0))
            w.writerow([n, squads.get(n, ""), "未到场", "", "", consec, cumul, "是" if kick_reason(n, abs_info) else ""])

    out_xlsx = ROOT / f"attendance_{date_str}.xlsx"
    try:
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "考勤"
        ws.append(["玩家名", "小队", "状态", "OCR文本", "相似度", "连续缺席", "累计缺席", "建议清退"])
        for name, raw, score, status in results:
            consec, cumul = abs_info.get(name, (0, 0))
            ws.append([name, squads.get(name, ""), "到场" if status == "ok" else "疑似", raw, score,
                       consec, cumul, "是" if kick_reason(name, abs_info) else ""])
        for n in absent:
            consec, cumul = abs_info.get(n, (0, 0))
            ws.append([n, squads.get(n, ""), "未到场", "", "", consec, cumul, "是" if kick_reason(n, abs_info) else ""])
        wb.save(out_xlsx)
    except Exception as e:
        print(f"[警告] 生成 xlsx 失败（CSV 已生成）：{e}")

    print(f"\n[考勤] {date_str}  到场 {len(present)} / 名册 {len(known)}，未到场 {len(absent)}")
    print(f"  CSV : {out_csv}")
    print(f"  表  : {out_xlsx}")
    print("  到场名单：")
    for name, raw, score, status in results:
        mark = "" if status == "ok" else " [疑似]"
        print(f"    ✓ {name}  (OCR「{raw}」 {score:.2f}){mark}")
    if absent:
        print("  未到场：", "、".join(absent))
    if dates:
        kicked = [n for n in known if kick_reason(n, abs_info)]
        print(f"\n[清退建议] 已记录 {len(dates)} 场活动；触发清退（连续≥{CONSEC_KICK} 或 累计≥{SEASON_ABSENT_CAP}）：")
        if kicked:
            for n in kicked:
                print(f"    ✗ {n} —— {kick_reason(n, abs_info)}")
        else:
            print("    暂无（都还安全）")


def append_case(img_path, items, results, date_str):
    CASES_DIR.mkdir(exist_ok=True)
    rec = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "date": date_str,
        "img": Path(img_path).name,
        "ocr_texts": [it["text"] for it in items],
        "names": [r[0] for r in results],
    }
    with open(CASES_DB, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[案例库] 已累积 1 条 → {CASES_DB}")


def cmd_cases(args):
    if args.export:
        out = Path(args.export)
        if not CASES_DB.exists():
            print("案例库为空，无内容可导出")
            return
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(CASES_DB, "cases.jsonl")
        print(f"[导出] 匿名案例包 → {out}（可分享给他人共同改进识别）")
        return
    if not CASES_DB.exists():
        print("案例库为空")
        return
    n = sum(1 for _ in open(CASES_DB, encoding="utf-8"))
    print(f"[案例库] 已累积 {n} 条样本。导出：python attendance.py cases --export cases.zip")


def main():
    ap = argparse.ArgumentParser(description="拉格朗日考勤开源版：本地识别截图，自动统计谁来了谁没来")
    sub = ap.add_subparsers(dest="cmd")

    r = sub.add_parser("recognize", help="识别活动考勤截图（纯名字名单 / 集合点星图，可多张）")
    r.add_argument("images", nargs="+", help="活动截图路径（可多张，集合点星图常需截好几张；自动合并到场名单）")
    r.add_argument("--roster", default=str(ROSTER), help="名册 csv（默认 roster.csv）")
    r.add_argument("--date", default=None, help="活动日期 YYYY-MM-DD")
    r.add_argument("--no-history", action="store_true",
                   help="仅本次识别，不写入历史（不累积连续/累计缺席统计）")
    r.add_argument("--type", default="auto",
                   choices=["auto", "attendance_list", "starmap", "member_list"],
                   help="截图类型（默认 auto 自动判断）")
    r.add_argument("--name-x-max", type=float, default=650, help="名字区域最大 x 坐标（名单模式用）")
    r.add_argument("--min-match", type=float, default=0.75)

    c = sub.add_parser("cases", help="案例库管理")
    c.add_argument("--export", default=None, help="导出匿名案例包 zip")
    c.add_argument("--stats", action="store_true")

    b = sub.add_parser("build-roster", help="从全盟截图一键生成名册（roster.csv）")
    b.add_argument("images", nargs="+", help="全盟成员截图路径（可多张，自动合并去重；成员列表或纯名字均可）")
    b.add_argument("--out", default=str(ROSTER), help="输出名册 csv（默认 roster.csv）")
    b.add_argument("--merge", action="store_true", default=True,
                   help="与已有 roster.csv 合并追加（默认）；分多次传图也不会丢人")
    b.add_argument("--overwrite", dest="merge", action="store_false",
                   help="覆盖已有 roster.csv 重建（清空旧名册从头来）")
    b.add_argument("--name-x-max", type=float, default=650, help="名字区域最大 x 坐标")

    args = ap.parse_args()
    if args.cmd == "recognize":
        cmd_recognize(args)
    elif args.cmd == "cases":
        cmd_cases(args)
    elif args.cmd == "build-roster":
        cmd_build_roster(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
