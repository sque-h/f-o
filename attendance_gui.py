#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拉格朗日考勤 · 一键版（本地网页 GUI）。

双击运行：在本地启动一个网页服务，浏览器自动打开，
点按钮选截图即可完成「建名册 / 考勤打卡 / 导出案例」，全程不用命令行。

技术：仅用 Python 标准库（http.server）+ attendance.py 已有依赖，无需 tkinter / flask。
打包：可用 PyInstaller 打成单个 exe，模型已随 rapidocr 包内，离线可用。
"""
import argparse
import base64
import io
import json
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import attendance as app

# ---------------------------------------------------------------------------
# 路径处理：未打包时输出到仓库；PyInstaller 冻结后输出到 exe 所在目录
# （_MEIPASS 是只读临时目录，不能写文件）。
# ---------------------------------------------------------------------------
if getattr(sys, "frozen", False):
    BASE = Path(sys.executable).resolve().parent
else:
    BASE = Path(__file__).resolve().parent

# 让 attendance 模块的全局路径指向可写目录（冻结后尤其重要）
app.ROOT = BASE
app.ROSTER = BASE / "roster.csv"
app.HISTORY_DIR = BASE / "history"
app.HISTORY_CSV = app.HISTORY_DIR / "attendance.csv"
app.CASES_DIR = BASE / "cases"
app.CASES_DB = app.CASES_DIR / "cases.jsonl"

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>拉格朗日考勤 · 一键版</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: "Microsoft YaHei", "PingFang SC", sans-serif; margin:0;
         background:#0f1420; color:#e8edf5; }
  header { background:linear-gradient(90deg,#1f6feb,#13c2c2); padding:18px 24px; }
  header h1 { margin:0; font-size:20px; }
  header p { margin:4px 0 0; font-size:13px; opacity:.9; }
  .wrap { max-width:880px; margin:0 auto; padding:20px; }
  .card { background:#192036; border:1px solid #2a3550; border-radius:12px;
          padding:18px; margin-bottom:18px; }
  .card h2 { margin:0 0 12px; font-size:16px; color:#7ee0ff; }
  .step { font-size:12px; color:#9fb0c8; margin-bottom:10px; line-height:1.6; }
  button { background:#1f6feb; color:#fff; border:0; border-radius:8px;
           padding:10px 16px; font-size:14px; cursor:pointer; }
  button:hover { background:#3b82f6; }
  button.alt { background:#2a3550; }
  input[type=date] { background:#0f1420; color:#e8edf5; border:1px solid #2a3550;
                     border-radius:6px; padding:8px; font-size:14px; }
  input[type=file] { color:#cdd8ea; font-size:13px; margin:8px 0; }
  .result { background:#0f1420; border-radius:8px; padding:12px; margin-top:12px;
            font-size:13px; white-space:pre-wrap; max-height:280px; overflow:auto; }
  .ok { color:#5ee08a; } .warn { color:#ffcc66; } .err { color:#ff7b7b; }
  a.dl { display:inline-block; margin-top:8px; color:#7ee0ff; text-decoration:none;
         border:1px solid #2a3550; padding:6px 12px; border-radius:6px; }
  a.dl:hover { background:#2a3550; }
  .pill { display:inline-block; background:#1f6feb; border-radius:12px;
          padding:2px 10px; font-size:12px; margin-left:6px; }
</style>
</head>
<body>
<header>
  <h1>拉格朗日考勤 · 一键版</h1>
  <p>本地识别截图，自动统计「谁来了谁没来」 · 纯离线 · 零封号风险</p>
</header>
<div class="wrap">

  <div class="card">
    <h2>第 1 步 · 建名册</h2>
    <div class="step">选一张「全盟成员列表」截图（可多选，名单太长分多张截也行）。
      工具自动识别玩家名和小队，生成 <b>roster.csv</b>。生成后请<b>核对一眼</b>（本地OCR偶有形近字误差）。
      <br><b>不会丢人</b>：默认与已有名册<b>合并追加</b>，分多次传图也不会覆盖之前的人；OCR 认错的名字可到第 1.5 步手动改。</div>
    <input type="file" id="rosterFiles" accept="image/*" multiple>
    <br><button onclick="buildRoster()">生成名册</button>
    <label style="margin-left:10px;font-size:12px;color:#9fb0c8">
      <input type="checkbox" id="rosterOverwrite"> 覆盖重建（清空旧名册从头来）</label>
    <div id="rosterResult" class="result" style="display:none"></div>
  </div>

  <div class="card">
    <h2>第 1.5 步 · 手动编辑 / 录入名册</h2>
    <div class="step">OCR 认错名字、或想纯手填（不截图）都在这改。
      表格里<b>增 / 删 / 改名 / 改小队</b>，改完点保存即写入 <b>roster.csv</b>。</div>
    <div style="margin:6px 0">
      <button class="alt" onclick="loadRoster()">载入当前名册</button>
      <button class="alt" onclick="addRow()">+ 新增一行</button>
      <button onclick="saveRoster()">保存名册</button>
    </div>
    <div id="rosterTable" style="max-height:280px;overflow:auto"></div>
    <div id="rosterEditResult" class="result" style="display:none"></div>
  </div>

  <div class="card">
    <h2>第 2 步 · 考勤打卡</h2>
    <div class="step">每次活动截一张图（纯名字名单 / 集合点星图均可，自动判断）。
      选图 + 填活动日期 → 自动比对名册，出结果表和累计缺席统计。</div>
    <input type="file" id="attFile" accept="image/*">
    <div style="margin:8px 0">活动日期：<input type="date" id="attDate"></div>
    <button onclick="recognize()">开始考勤</button>
    <label style="margin-left:10px;font-size:12px;color:#9fb0c8">
      <input type="checkbox" id="noHistory"> 仅本次（不累积历史）</label>
    <div id="attResult" class="result" style="display:none"></div>
  </div>

  <div class="card">
    <h2>第 3 步 · 案例库（可选）</h2>
    <div class="step">每次识别会匿名累积样本（不含你的联盟数据），导出后分享给作者/社区，
      一起把识别做得更准。</div>
    <button class="alt" onclick="exportCases()">导出匿名案例包</button>
    <div id="caseResult" class="result" style="display:none"></div>
  </div>

</div>
<script>
function b64(file){return new Promise(r=>{const fr=new FileReader();
  fr.onload=()=>r(fr.result.split(',')[1]);fr.readAsDataURL(file);});}

async function postJSON(url, obj){
  const r = await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(obj)});
  return await r.json();
}
function show(el, html, cls){const d=document.getElementById(el);
  d.style.display='block';d.className='result '+(cls||'');d.innerHTML=html;}

async function buildRoster(){
  const files=document.getElementById('rosterFiles').files;
  if(!files.length){show('rosterResult','请先选择截图','warn');return;}
  const imgs=[];for(const f of files){imgs.push({name:f.name,data:await b64(f)});}
  const overwrite=document.getElementById('rosterOverwrite').checked;
  show('rosterResult','识别中…（首次可能需十几秒加载模型）');
  const j=await postJSON('/api/roster',{images:imgs,overwrite:overwrite});
  if(j.ok){let h='✅ 已生成名册：<b>'+j.count+'</b> 人'
    +(j.merged?('（其中合并保留 '+j.merged+' 人）'):'')+'<br><a class="dl" href="/download?f='+
    encodeURIComponent(j.roster_file)+'">下载 roster.csv</a><br><br>';
    h+='<span class="ok">前若干名预览：</span><br>'+j.names.map(n=>'· '+n).join('<br>');
    show('rosterResult',h,'ok');}
  else show('rosterResult','❌ '+j.error,'err');
}

function rosterRowHTML(name,squad){
  return '<div class="rrow" style="display:flex;gap:8px;margin:4px 0;align-items:center">'
    +'<input class="rn" value="'+(name||'')+'" placeholder="玩家名" style="flex:2;background:#0f1420;color:#e8edf5;border:1px solid #2a3550;border-radius:6px;padding:6px">'
    +'<input class="rs" value="'+(squad||'')+'" placeholder="小队" style="flex:2;background:#0f1420;color:#e8edf5;border:1px solid #2a3550;border-radius:6px;padding:6px">'
    +'<button class="alt" onclick="delRow(this)" style="padding:6px 10px">删</button></div>';
}

async function loadRoster(){
  show('rosterEditResult','载入中…');
  const j=await postJSON('/api/roster_get',{});
  if(j.ok){
    const box=document.getElementById('rosterTable');
    box.innerHTML='';
    if(!j.rows.length){box.innerHTML='<div style="color:#9fb0c8;font-size:13px">名册为空，点「+ 新增一行」手填。</div>';}
    for(const r of j.rows){box.insertAdjacentHTML('beforeend',rosterRowHTML(r.name,r.squad));}
    show('rosterEditResult','已载入 <b>'+j.rows.length+'</b> 人','ok');
  } else show('rosterEditResult','❌ '+j.error,'err');
}

function addRow(){document.getElementById('rosterTable').insertAdjacentHTML('beforeend',rosterRowHTML('',''));}

function delRow(btn){btn.parentElement.remove();}

async function saveRoster(){
  const box=document.getElementById('rosterTable');
  const rows=[];let dup=false,seen={};
  box.querySelectorAll('.rrow').forEach(d=>{
    const n=d.querySelector('.rn').value.trim();
    const s=d.querySelector('.rs').value.trim();
    if(n){if(seen[n]){dup=true;}seen[n]=1;rows.push({name:n,squad:s});}
  });
  if(dup){show('rosterEditResult','⚠ 有重复玩家名，请先合并再保存','warn');return;}
  show('rosterEditResult','保存中…');
  const j=await postJSON('/api/roster_save',{rows:rows});
  if(j.ok){show('rosterEditResult','✅ 已保存名册：<b>'+j.count+'</b> 人（已写入 roster.csv）','ok');}
  else show('rosterEditResult','❌ '+j.error,'err');
}

async function recognize(){
  const f=document.getElementById('attFile').files[0];
  if(!f){show('attResult','请先选择活动截图','warn');return;}
  const date=document.getElementById('attDate').value||'';
  const noH=document.getElementById('noHistory').checked;
  show('attResult','识别中…');
  const j=await postJSON('/api/recognize',{image:{name:f.name,data:await b64(f)},date:date,no_history:noH});
  if(j.ok){let h='✅ '+j.date+'　到场 <b>'+j.present.length+'</b> / 名册 <b>'+j.total+
    '</b>　未到场 <b>'+j.absent.length+'</b><br>'+
    '<a class="dl" href="/download?f='+encodeURIComponent(j.xlsx)+'">下载 Excel 表</a> '+
    '<a class="dl" href="/download?f='+encodeURIComponent(j.csv)+'">下载 CSV</a><br><br>';
    if(j.present.length){h+='<span class="ok">到场：</span><br>'+j.present.map(n=>'✓ '+n).join('、')+'<br><br>';}
    if(j.absent.length){h+='<span class="err">未到场：</span><br>'+j.absent.map(n=>'✗ '+n).join('、')+'<br><br>';}
    if(j.kicked.length){h+='<span class="err">⚠ 建议清退（'+j.kicked.length+'人）：</span><br>'+j.kicked.join('、');}
    else h+='<span class="ok">暂无触发清退</span>';
    show('attResult',h,'ok');}
  else show('attResult','❌ '+j.error,'err');
}

async function exportCases(){
  show('caseResult','导出中…');
  const j=await postJSON('/api/export',{});
  if(j.ok){show('caseResult','✅ 已导出：<a class="dl" href="/download?f='+
    encodeURIComponent(j.file)+'">下载 cases.zip</a>','ok');}
  else show('caseResult','❌ '+j.error,'err');
}

// 默认日期填今天
document.getElementById('attDate').value=new Date().toISOString().slice(0,10);
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# 业务逻辑（复用 attendance 模块，捕获 stdout 作为日志）
# ---------------------------------------------------------------------------
def _capture_stdout(func, *a, **kw):
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        func(*a, **kw)
    finally:
        sys.stdout = old
    return buf.getvalue()


def _load_roster_names():
    known, _ = app.load_roster(app.ROSTER)
    return known


def do_build_roster(images_b64, overwrite=False):
    import tempfile
    paths = []
    for i, im in enumerate(images_b64):
        p = BASE / f"_up_roster_{i}.png"
        p.write_bytes(base64.b64decode(im["data"]))
        paths.append(str(p))
    out = str(BASE / "roster.csv")
    args = argparse.Namespace(images=paths, out=out, name_x_max=650.0, merge=not overwrite)
    before = len(_load_roster_names())
    log = _capture_stdout(app.cmd_build_roster, args)
    for p in paths:
        try: os.remove(p)
        except OSError: pass
    known = _load_roster_names()
    merged = (before if (not overwrite and before) else 0)
    return {"ok": True, "count": len(known), "names": known[:50],
            "merged": merged,
            "roster_file": "roster.csv", "log": log}


def do_get_roster():
    known, squads = app.load_roster(app.ROSTER)
    rows = [{"name": n, "squad": squads.get(n, "")} for n in known]
    return {"ok": True, "rows": rows}


def do_save_roster(rows):
    rows = rows or []
    seen = set()
    cleaned = []
    for r in rows:
        nm = (r.get("name") or "").strip()
        sq = (r.get("squad") or "").strip()
        if not nm or nm in seen:
            continue
        seen.add(nm)
        cleaned.append((nm, sq))
    out = app.ROSTER
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        import csv
        w = csv.writer(f)
        w.writerow(["玩家名", "小队"])
        for nm, sq in cleaned:
            w.writerow([nm, sq])
    return {"ok": True, "count": len(cleaned)}


def do_recognize(image_b64, date, no_history):
    p = BASE / "_up_att.png"
    p.write_bytes(base64.b64decode(image_b64["data"]))
    args = argparse.Namespace(
        image=str(p), roster=str(app.ROSTER), date=(date or None),
        no_history=bool(no_history), type="auto", name_x_max=650.0, min_match=0.75,
    )
    log = _capture_stdout(app.cmd_recognize, args)
    try: os.remove(p)
    except OSError: pass
    # 读取生成的考勤结果
    import csv
    known = _load_roster_names()
    date_str = date or __import__("datetime").datetime.now().strftime("%Y-%m-%d")
    csv_path = BASE / f"attendance_{date_str}.csv"
    xlsx_path = BASE / f"attendance_{date_str}.xlsx"
    present, absent, kicked = [], [], []
    if csv_path.exists():
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                nm = row.get("玩家名", "").strip()
                st = row.get("状态", "")
                if st == "到场" or st == "疑似":
                    present.append(nm)
                elif st == "未到场":
                    absent.append(nm)
                if (row.get("建议清退") or "").strip() == "是":
                    kicked.append(nm)
    return {
        "ok": True, "date": date_str, "total": len(known),
        "present": present, "absent": absent, "kicked": kicked,
        "csv": csv_path.name if csv_path.exists() else "",
        "xlsx": xlsx_path.name if xlsx_path.exists() else "",
        "log": log,
    }


def do_export_cases():
    args = argparse.Namespace(export=str(BASE / "cases.zip"), stats=False)
    log = _capture_stdout(app.cmd_cases, args)
    zp = BASE / "cases.zip"
    if zp.exists():
        return {"ok": True, "file": "cases.zip", "log": log}
    return {"ok": False, "error": "案例库为空，无内容可导出"}


# ---------------------------------------------------------------------------
# HTTP 服务
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 静默
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False)
            ctype = "application/json"
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/" or u.path == "":
            self._send(200, INDEX_HTML, "text/html")
        elif u.path == "/download":
            q = parse_qs(u.query)
            name = q.get("f", [""])[0]
            # 仅允许下载 BASE 目录下的安全文件名
            safe = Path(name).name
            fp = (BASE / safe)
            if fp.exists() and fp.parent == BASE and safe.lower().endswith((".csv", ".xlsx", ".zip")):
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", f'attachment; filename="{safe}"')
                data = fp.read_bytes()
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self._send(404, {"ok": False, "error": "文件不存在"})
        else:
            self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            payload = {}
        try:
            if u.path == "/api/roster":
                res = do_build_roster(payload.get("images", []), payload.get("overwrite", False))
            elif u.path == "/api/roster_get":
                res = do_get_roster()
            elif u.path == "/api/roster_save":
                res = do_save_roster(payload.get("rows", []))
            elif u.path == "/api/recognize":
                res = do_recognize(payload.get("image", {}), payload.get("date", ""),
                                   payload.get("no_history", False))
            elif u.path == "/api/export":
                res = do_export_cases()
            else:
                res = {"ok": False, "error": "unknown api"}
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        self._send(200, res)


def run_server(open_browser=True, port=8765):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"[考勤一键版] 已在本地启动：{url}")
    print("[考勤一键版] 关闭本窗口即停止服务。")
    if open_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


# ---------------------------------------------------------------------------
# 自检模式（无界面，供打包前验证）
# ---------------------------------------------------------------------------
def selftest(roster_img=None, att_img=None):
    print("=== 自检：导入 ===")
    import ocr_local, parse_names  # noqa
    print("  attendance / ocr_local / parse_names 导入 OK")
    print("=== 自检：HTTP 服务 ===")
    import urllib.request
    srv = ThreadingHTTPServer(("127.0.0.1", 8799), Handler)
    import threading
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    html = urllib.request.urlopen("http://127.0.0.1:8799/").read().decode("utf-8")
    assert "拉格朗日考勤" in html, "首页未正常返回"
    print("  首页返回 OK")
    srv.shutdown()
    if roster_img and att_img:
        print("=== 自检：真实截图流程 ===")
        r = do_build_roster([{"name": "m.png", "data": base64.b64encode(Path(roster_img).read_bytes()).decode()}])
        print("  build-roster:", r["count"], "人", "OK" if r["ok"] else r.get("error"))
        a = do_recognize({"name": "a.png", "data": base64.b64encode(Path(att_img).read_bytes()).decode()}, "", False)
        print("  recognize: 到场", len(a["present"]), "/ 名册", a["total"], "OK" if a["ok"] else a.get("error"))
    print("=== 自检完成 ===")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--selftest", action="store_true", help="无界面自检")
    ap.add_argument("--selftest-roster", default=None)
    ap.add_argument("--selftest-recognize", default=None)
    a = ap.parse_args()
    if a.selftest:
        selftest(a.selftest_roster, a.selftest_recognize)
    else:
        run_server(open_browser=not a.no_browser, port=a.port)
