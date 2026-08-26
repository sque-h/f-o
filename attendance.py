#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拉格朗日考勤 · 开源版（考勤1.0 阉割引流版）主入口。

功能（按完整度切，只留考勤核心）：
  - 纯本地 OCR 识别名字（RapidOCR，零密钥）
  - 单格式：纯名字考勤截图（谁来了谁没来）
  - 输出 CSV + 一张本地表（xlsx）
  - 案例库自动累积（cases/），可导出回传作者更新中心库

用法：
  python attendance.py recognize <截图.png> [--roster roster.csv] [--date 2026-08-26]
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


def cmd_recognize(args):
    known, squads = load_roster(Path(args.roster))
    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    items = ocr_local.ocr_image(args.image)
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
        print(f"[导出] 匿名案例包 → {out}（发给作者 sque-h 更新中心库）")
        return
    if not CASES_DB.exists():
        print("案例库为空")
        return
    n = sum(1 for _ in open(CASES_DB, encoding="utf-8"))
    print(f"[案例库] 已累积 {n} 条样本。导出：python attendance.py cases --export cases.zip")


def main():
    ap = argparse.ArgumentParser(description="拉格朗日考勤开源版（考勤1.0 阉割引流版）")
    sub = ap.add_subparsers(dest="cmd")

    r = sub.add_parser("recognize", help="识别一张纯名字考勤截图")
    r.add_argument("image", help="截图路径")
    r.add_argument("--roster", default=str(ROSTER), help="名册 csv（默认 roster.csv）")
    r.add_argument("--date", default=None, help="活动日期 YYYY-MM-DD")
    r.add_argument("--name-x-max", type=float, default=650, help="名字区域最大 x 坐标")
    r.add_argument("--min-match", type=float, default=0.75)

    c = sub.add_parser("cases", help="案例库管理")
    c.add_argument("--export", default=None, help="导出匿名案例包 zip")
    c.add_argument("--stats", action="store_true")

    args = ap.parse_args()
    if args.cmd == "recognize":
        cmd_recognize(args)
    elif args.cmd == "cases":
        cmd_cases(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
