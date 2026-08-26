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


def cmd_build_roster(args):
    roster = []
    for img in args.images:
        items = ocr_local.ocr_image(img)
        roster += pn.extract_roster(items, name_x_max=args.name_x_max)
    # 多张截图合并：按名字去重（保留首次出现），名单长分多张截自动拼
    seen, merged = set(), []
    for name, team in roster:
        if name in seen:
            continue
        seen.add(name)
        merged.append((name, team))
    roster = merged
    out = Path(args.out)
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
    items = ocr_local.ocr_image(args.image)

    # 自动判断截图类型：纯名字名单 / 集合点星图（图片）/ 成员列表(应走 build-roster)
    cls = args.type if args.type and args.type != "auto" else pn.classify(items)
    if cls == "member_list":
        print("\n[提示] 这张图是「成员列表」（含繁荣度/小队列头），"
              "请改用 build-roster 生成名册；\n        或换一张活动到场截图"
              "（纯名字名单 / 集合点星图）再 recognize。")
        return
    if cls == "starmap":
        print("[识别] 检测到集合点星图，按星图模式提取名字…")
        results = pn.extract_names_starmap(items, known, min_match=args.min_match)
    else:
        if cls == "attendance_list":
            print("[识别] 检测到纯名字名单，按名单模式提取…")
        results = pn.extract_names(
            items, known, name_x_max=args.name_x_max, min_match=args.min_match
        )

    present = {r[0] for r in results if r[3] == "ok"}
    absent = [n for n in known if n not in present]

    out_csv = ROOT / f"attendance_{date_str}.csv"
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["玩家名", "小队", "状态", "OCR文本", "相似度"])
        for name, raw, score, status in results:
            w.writerow([name, squads.get(name, ""), "到场" if status == "ok" else "疑似", raw, score])
        for n in absent:
            w.writerow([n, squads.get(n, ""), "未到场", "", ""])

    out_xlsx = ROOT / f"attendance_{date_str}.xlsx"
    try:
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "考勤"
        ws.append(["玩家名", "小队", "状态", "OCR文本", "相似度"])
        for name, raw, score, status in results:
            ws.append([name, squads.get(name, ""), "到场" if status == "ok" else "疑似", raw, score])
        for n in absent:
            ws.append([n, squads.get(n, ""), "未到场", "", ""])
        wb.save(out_xlsx)
    except Exception as e:
        print(f"[警告] 生成 xlsx 失败（CSV 已生成）：{e}")

    append_case(args.image, items, results, date_str)

    print(f"\n[考勤] {date_str}  到场 {len(present)} / 名册 {len(known)}，未到场 {len(absent)}")
    print(f"  CSV : {out_csv}")
    print(f"  表  : {out_xlsx}")
    print("  到场名单：")
    for name, raw, score, status in results:
        mark = "" if status == "ok" else " [疑似]"
        print(f"    ✓ {name}  (OCR「{raw}」 {score:.2f}){mark}")
    if absent:
        print("  未到场：", "、".join(absent))


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

    r = sub.add_parser("recognize", help="识别一张活动考勤截图（纯名字名单 / 集合点星图）")
    r.add_argument("image", help="截图路径")
    r.add_argument("--roster", default=str(ROSTER), help="名册 csv（默认 roster.csv）")
    r.add_argument("--date", default=None, help="活动日期 YYYY-MM-DD")
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
