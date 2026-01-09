# services/inspect/runner.py
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout

from services.inspect.models import InspectItem, InspectReport, InspectSummary
from services.inspect import checks


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}-{uuid.uuid4().hex[:8]}"


def _html_escape(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _level_rank(level: str) -> int:
    # 越小越严重
    if level == "error":
        return 0
    if level == "warn":
        return 1
    if level == "skip":
        return 3
    return 2  # ok


def _guess_group(key: str) -> str:
    k = (key or "").lower()
    # 你这套 key 命名里通常含 group 前缀
    for g in ("prom", "nodes", "system", "pods", "events", "storage", "dns"):
        if k.startswith(g) or f"_{g}" in k or g in k:
            return g
    return "other"


def _score(summary: InspectSummary) -> int:
    # 简单评分：Error 扣 20，Warn 扣 8，Skip 不扣，最低 0
    s = 100 - summary.error * 20 - summary.warn * 8
    if s < 0:
        s = 0
    if s > 100:
        s = 100
    return int(s)


def render_html(report: InspectReport) -> str:
    s = report.summary
    score = _score(s)

    score_label = "优秀"
    score_class = "good"
    if score < 90:
        score_label = "良好"
        score_class = "ok"
    if score < 75:
        score_label = "关注"
        score_class = "warn"
    if score < 60:
        score_label = "风险"
        score_class = "bad"

    # 预分组：group -> items
    groups: Dict[str, List[InspectItem]] = {}
    for it in report.items:
        g = _guess_group(it.key)
        groups.setdefault(g, []).append(it)

    # 分组排序：把常见组放前
    group_order = ["nodes", "system", "pods", "events", "storage", "dns", "prom", "other"]
    ordered_groups = sorted(groups.keys(), key=lambda x: group_order.index(x) if x in group_order else 999)

    # 行渲染（每行带 data-* 便于前端筛选/搜索）
    def badge(level: str) -> str:
        text = (level or "").upper()
        return f'<span class="badge {level}">{_html_escape(text)}</span>'

    rows_by_group: Dict[str, str] = {}

    for g in ordered_groups:
        rows = []
        for it in groups[g]:
            ev = json.dumps(it.evidence or {}, ensure_ascii=False, indent=2)
            ev_escaped = _html_escape(ev)
            detail = _html_escape(it.detail or "")
            sug = _html_escape(getattr(it, "suggestion", None) or "")

            dur = int(getattr(it, "durationMs", 0) or 0)
            title = _html_escape(it.title or it.key)
            key = _html_escape(it.key or "")

            # 方便搜索：把 title/key/detail/suggestion 合并到 data-text
            search_text = _html_escape(f"{it.title} {it.key} {it.level} {it.detail or ''} {getattr(it, 'suggestion', '')}")

            rows.append(
                f"""
<tr class="row" data-level="{_html_escape(it.level)}" data-group="{_html_escape(g)}" data-text="{search_text}">
  <td class="col-item">
    <div class="title">{title}</div>
    <div class="sub">{key}</div>
  </td>
  <td class="col-level">{badge(it.level)}</td>
  <td class="col-detail">
    <div>{detail or '-'}</div>
    {"<div class='suggest'><span class='tag'>建议</span> " + sug + "</div>" if sug else ""}
  </td>
  <td class="col-ev">
    <details>
      <summary>查看</summary>
      <pre class="pre">{ev_escaped}</pre>
      <div class="ev-actions">
        <button class="btn tiny" type="button" onclick="copyText(this)">复制 JSON</button>
      </div>
    </details>
  </td>
  <td class="col-dur">{dur} ms</td>
</tr>
"""
            )
        rows_by_group[g] = "\n".join(rows)

    # 把 report 的 JSON 数据内嵌，方便复制/导出（不依赖后端）
    report_json = json.dumps(report.model_dump(), ensure_ascii=False, indent=2)
    report_json_escaped = _html_escape(report_json)

    updated_at = _html_escape(report.updatedAt)
    run_id = _html_escape(report.runId)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>K3s 巡检报告 · {run_id}</title>
<style>
  :root{{
    --bg0:#f7fafc;
    --bg1:#ffffff;
    --panel:#ffffff;
    --panel2:#f8fafc;
    --text:#0f172a;
    --muted:#64748b;
    --line:#e2e8f0;

    --ok:#16a34a;
    --warn:#f59e0b;
    --error:#ef4444;
    --skip:#94a3b8;
    --blue:#2563eb;

    --shadow: 0 12px 30px rgba(2, 8, 23, 0.08);
  }}

  *{{ box-sizing:border-box; }}
  body{{
    margin:0;
    color:var(--text);
    font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, "PingFang SC","Hiragino Sans GB","Microsoft YaHei", Arial, sans-serif;
    background:
      radial-gradient(1200px 700px at 15% 0%, rgba(59,130,246,.18), transparent 55%),
      radial-gradient(900px 600px at 85% 10%, rgba(34,197,94,.14), transparent 55%),
      radial-gradient(900px 600px at 70% 90%, rgba(245,158,11,.12), transparent 55%),
      linear-gradient(180deg, var(--bg0), #eef2ff 55%, #f7fafc);
  }}
  a{{ color:var(--blue); text-decoration:none; }}

  .wrap{{ max-width:1180px; margin:0 auto; padding:22px 18px 36px; }}

  .top{{
    display:flex; align-items:flex-start; justify-content:space-between; gap:16px;
    margin-bottom:14px;
  }}
  .h1{{ font-size:22px; font-weight:900; letter-spacing:.2px; margin:0 0 6px; }}
  .meta{{ color:var(--muted); font-size:12px; line-height:1.5; }}

  .actions{{ display:flex; gap:10px; flex-wrap:wrap; justify-content:flex-end; }}

  .btn{{
    border:1px solid var(--line);
    background:rgba(255,255,255,.75);
    color:var(--text);
    padding:8px 10px;
    border-radius:12px;
    cursor:pointer;
    font-size:12px;
    box-shadow: 0 2px 10px rgba(2,8,23,0.04);
  }}
  .btn:hover{{ background:rgba(255,255,255,.95); }}
  .btn.primary{{ border-color: rgba(37,99,235,.35); }}

  .grid{{
    display:grid;
    grid-template-columns: 1.2fr 1fr;
    gap:14px;
    margin:10px 0 14px;
  }}
  @media (max-width:980px){{
    .grid{{ grid-template-columns:1fr; }}
    .top{{ flex-direction:column; }}
    .actions{{ justify-content:flex-start; }}
  }}

  .card{{
    background: rgba(255,255,255,0.78);
    border:1px solid var(--line);
    border-radius:18px;
    padding:14px 14px;
    box-shadow: var(--shadow);
    backdrop-filter: blur(10px);
  }}

  .score{{ display:flex; gap:12px; align-items:center; }}

  .ring{{ 
    width:74px; height:74px; border-radius:999px;
    display:flex; align-items:center; justify-content:center;
    background: conic-gradient(
      var(--ok) 280deg,
      rgba(15,23,42,0.08) 0
    );
    position:relative;
  }}
  .ring::after{{ 
    content:"";
    position:absolute; inset:7px;
    border-radius:999px;
    background: rgba(255,255,255,0.9);
    border:1px solid rgba(226,232,240,0.9);
  }}
  .ring b{{  position:relative; font-size:18px; }}

  .score .txt .label{{  font-size:12px; color:var(--muted); margin-bottom:2px; }}
  .score .txt .big{{  font-size:16px; font-weight:900; }}

  .pillbar{{  margin-top:10px; display:flex; gap:10px; flex-wrap:wrap; }}
  .pill{{ 
    border:1px solid var(--line);
    background: rgba(255,255,255,.85);
    padding:10px 12px;
    border-radius:16px;
    min-width:120px;
    box-shadow: 0 8px 20px rgba(2,8,23,0.05);
  }}
  .pill .k{{  color:var(--muted); font-size:12px; }}
  .pill .v{{  font-size:18px; font-weight:900; margin-top:2px; }}
  .pill .v.ok{{  color:var(--ok); }}
  .pill .v.warn{{  color:var(--warn); }}
  .pill .v.error{{  color:var(--error); }}
  .pill .v.skip{{  color:var(--skip); }}

  .filters{{  display:flex; gap:10px; flex-wrap:wrap; align-items:center; margin-top:8px; }}

  .input,.select{{ 
    border:1px solid var(--line);
    background: rgba(255,255,255,.85);
    color: var(--text);
    padding:9px 10px;
    border-radius:14px;
    outline:none;
    box-shadow: 0 6px 18px rgba(2,8,23,0.05);
  }}
  .input{{  flex:1; min-width:220px; }}

  .section{{  margin-top:14px; }}
  .section h2{{  margin:12px 0 10px; font-size:14px; color: rgba(15,23,42,0.9); letter-spacing:.2px; }}

  .group{{ 
    border:1px solid var(--line);
    background: rgba(255,255,255,0.78);
    border-radius:18px;
    overflow:hidden;
    margin-bottom:12px;
    box-shadow: var(--shadow);
  }}
  .group-head{{ 
    display:flex; align-items:center; justify-content:space-between;
    padding:12px 14px;
    cursor:pointer; user-select:none;
    background: rgba(248,250,252,0.9);
  }}
  .group-head:hover{{  background: rgba(241,245,249,1); }}

  .group-title{{ 
    display:flex; gap:10px; align-items:center;
    font-weight:900; font-size:13px;
  }}
  .group-badges{{  display:flex; gap:8px; align-items:center; color:var(--muted); font-size:12px; }}

  .caret{{ 
    width:10px; height:10px;
    border-right:2px solid rgba(100,116,139,0.9);
    border-bottom:2px solid rgba(100,116,139,0.9);
    transform: rotate(45deg);
    margin-left:8px;
  }}

  table{{  width:100%; border-collapse:collapse; }}
  thead th{{ 
    position:sticky;
    top:0;
    background: rgba(255,255,255,0.95);
    backdrop-filter: blur(8px);
    border-bottom:1px solid var(--line);
    z-index:2;
  }}
  th,td{{ 
    padding:10px 12px;
    border-bottom:1px solid rgba(226,232,240,0.9);
    vertical-align:top;
    font-size:13px;
  }}

  .col-item .title{{  font-weight:900; margin-bottom:3px; }}
  .col-item .sub{{  color:var(--muted); font-size:12px; }}

  .badge{{ 
    display:inline-flex; align-items:center; justify-content:center;
    padding:4px 8px;
    border-radius:999px;
    font-weight:900;
    font-size:11px;
    letter-spacing:.4px;
    border:1px solid rgba(2,8,23,0.08);
    background: rgba(2,8,23,0.03);
  }}
  .badge.ok{{  color:var(--ok); border-color: rgba(22,163,74,0.25); background: rgba(22,163,74,0.10); }}
  .badge.warn{{  color:var(--warn); border-color: rgba(245,158,11,0.30); background: rgba(245,158,11,0.12); }}
  .badge.error{{  color:var(--error); border-color: rgba(239,68,68,0.30); background: rgba(239,68,68,0.10); }}
  .badge.skip{{  color:var(--skip); border-color: rgba(148,163,184,0.30); background: rgba(148,163,184,0.12); }}

  .suggest{{ 
    margin-top:8px;
    padding:8px 10px;
    border-radius:14px;
    border:1px dashed rgba(148,163,184,0.6);
    background: rgba(241,245,249,0.85);
    color: rgba(15,23,42,0.85);
  }}
  .tag{{ 
    display:inline-block;
    font-size:11px;
    padding:2px 6px;
    border-radius:999px;
    color: rgba(15,23,42,0.85);
    border:1px solid rgba(148,163,184,0.5);
    background: rgba(255,255,255,0.8);
    margin-right:6px;
  }}

  details > summary{{  cursor:pointer; color: var(--blue); user-select:none; }}

  .pre{{ 
    margin:10px 0 6px;
    padding:10px 12px;
    border-radius:14px;
    border:1px solid rgba(226,232,240,0.9);
    background: rgba(248,250,252,0.95);
    overflow:auto;
    max-height:320px;
    font-size:12px;
    line-height:1.45;
    color: rgba(15,23,42,0.9);
  }}

  .ev-actions{{  display:flex; gap:8px; }}
  .muted{{  color:var(--muted); font-size:12px; }}
  .footer{{  margin-top:14px; color: var(--muted); font-size:12px; }}
  .hidden{{  display:none !important; }}
</style>

</head>
<body>
  <div class="wrap">
    <div class="top">
      <div>
        <div class="h1">K3s 一键巡检报告</div>
        <div class="meta">
          runId: <code>{run_id}</code> · updatedAt: <code>{updated_at}</code> · duration: <code>{int(report.durationMs)} ms</code>
        </div>
      </div>
      <div class="actions">
        <button class="btn primary" type="button" onclick="copyAll()">复制整份报告 JSON</button>
        <button class="btn" type="button" onclick="expandAll(true)">展开全部 evidence</button>
        <button class="btn" type="button" onclick="expandAll(false)">收起全部 evidence</button>
      </div>
    </div>

    <div class="grid">
      <div class="card">
        <div class="score">
          <div class="ring"><b>{score}</b></div>
          <div class="txt">
            <div class="label">健康评分</div>
            <div class="big">{_html_escape(score_label)} <span class="muted">（{_html_escape(score_class)}）</span></div>
            <div class="muted" style="margin-top:6px;">
              评分规则：Error -20 / Warn -8（最低 0）
            </div>
          </div>
        </div>
        <div class="pillbar">
          <div class="pill"><div class="k">总项</div><div class="v">{s.total}</div></div>
          <div class="pill"><div class="k">OK</div><div class="v ok">{s.ok}</div></div>
          <div class="pill"><div class="k">WARN</div><div class="v warn">{s.warn}</div></div>
          <div class="pill"><div class="k">ERROR</div><div class="v error">{s.error}</div></div>
          <div class="pill"><div class="k">SKIP</div><div class="v skip">{s.skip}</div></div>
        </div>
      </div>

      <div class="card">
        <div style="font-weight:800;margin-bottom:8px;">筛选与搜索</div>
        <div class="filters">
          <input id="q" class="input" placeholder="搜索：key/title/detail/suggestion..." oninput="applyFilter()" />
          <select id="lv" class="select" onchange="applyFilter()">
            <option value="all">级别：全部</option>
            <option value="error">只看 ERROR</option>
            <option value="warn">只看 WARN+</option>
            <option value="ok">只看 OK</option>
            <option value="skip">只看 SKIP</option>
          </select>
          <select id="gp" class="select" onchange="applyFilter()">
            <option value="all">分组：全部</option>
            {''.join([f'<option value="{_html_escape(g)}">{_html_escape(g)}</option>' for g in ordered_groups])}
          </select>
          <button class="btn" type="button" onclick="resetFilter()">重置</button>
        </div>
        <div class="footer">
          提示：若出现 “权限不足/需要 RBAC: …”，给巡检凭据增加对应 list/get 权限。
        </div>
      </div>
    </div>

    <div class="section">
      <h2>巡检项明细（按分组）</h2>

      {"".join([
        f'''
        <div class="group" data-groupwrap="{_html_escape(g)}">
          <div class="group-head" onclick="toggleGroup('{_html_escape(g)}')">
            <div class="group-title">
              <span>{_html_escape(g)}</span>
              <span class="caret" id="caret_{_html_escape(g)}"></span>
            </div>
            <div class="group-badges">
              <span class="muted" id="cnt_{_html_escape(g)}"></span>
            </div>
          </div>
          <div class="group-body" id="body_{_html_escape(g)}">
            <table>
              <thead>
                <tr>
                  <th style="width:28%;">巡检项</th>
                  <th style="width:10%;">级别</th>
                  <th>详情</th>
                  <th style="width:18%;">证据</th>
                  <th style="width:10%;">耗时</th>
                </tr>
              </thead>
              <tbody>
                {rows_by_group[g]}
              </tbody>
            </table>
          </div>
        </div>
        '''
        for g in ordered_groups
      ])}
    </div>

    <div class="footer">
      生成时间：<code>{updated_at}</code> · runId：<code>{run_id}</code>
    </div>

    <textarea id="alljson" class="hidden">{report_json_escaped}</textarea>
  </div>

<script>
  function norm(s) {{ return (s||"").toString().toLowerCase().trim(); }}

  function applyFilter() {{
    const q = norm(document.getElementById("q").value);
    const lv = document.getElementById("lv").value;
    const gp = document.getElementById("gp").value;

    const rows = document.querySelectorAll("tr.row");
    let visible = 0;

    rows.forEach(r => {{
      const level = r.getAttribute("data-level") || "";
      const group = r.getAttribute("data-group") || "";
      const text = norm(r.getAttribute("data-text") || "");

      let ok = true;

      if (q && text.indexOf(q) === -1) ok = false;

      if (gp !== "all" && group !== gp) ok = false;

      if (lv === "error") {{
        if (level !== "error") ok = false;
      }} else if (lv === "warn") {{
        if (!(level === "warn" || level === "error")) ok = false;
      }} else if (lv === "ok") {{
        if (level !== "ok") ok = false;
      }} else if (lv === "skip") {{
        if (level !== "skip") ok = false;
      }}

      r.classList.toggle("hidden", !ok);
      if (ok) visible++;
    }});

    refreshGroupCounts();
  }}

  function resetFilter() {{
    document.getElementById("q").value = "";
    document.getElementById("lv").value = "all";
    document.getElementById("gp").value = "all";
    applyFilter();
  }}

  function toggleGroup(g) {{
    const body = document.getElementById("body_" + g);
    const caret = document.getElementById("caret_" + g);
    const hidden = body.style.display === "none";
    body.style.display = hidden ? "" : "none";
    caret.style.transform = hidden ? "rotate(45deg)" : "rotate(-135deg)";
  }}

  function expandAll(open) {{
    const ds = document.querySelectorAll("details");
    ds.forEach(d => d.open = !!open);
  }}

  function copyText(btn) {{
    // 找到同一 details 下的 pre
    const pre = btn.closest("details").querySelector("pre");
    navigator.clipboard.writeText(pre.innerText || "").then(() => {{
      btn.innerText = "已复制";
      setTimeout(()=>btn.innerText="复制 JSON", 900);
    }});
  }}

  function copyAll() {{
    const t = document.getElementById("alljson").value || "";
    navigator.clipboard.writeText(t).then(() => {{
      alert("已复制整份报告 JSON");
    }});
  }}

function refreshGroupCounts() {{
  const wraps = document.querySelectorAll("[data-groupwrap]");
  wraps.forEach(w => {{
    const g = w.getAttribute("data-groupwrap");
    const rows = w.querySelectorAll("tr.row");
    let ok=0,warn=0,error=0,skip=0,vis=0;

    rows.forEach(r => {{
      const hidden = r.classList.contains("hidden");
      const lv = r.getAttribute("data-level");
      if (!hidden) vis++;
      if (lv === "ok") ok++;
      else if (lv === "warn") warn++;
      else if (lv === "error") error++;
      else if (lv === "skip") skip++;
    }});

    const el = document.getElementById("cnt_" + g);
    if (el) {{
      el.innerText = "可见 " + vis + " · OK " + ok + " · WARN " + warn + " · ERROR " + error + " · SKIP " + skip;
    }}
  }});
}}


  // 初始：折叠非严重项组可以按需改，这里默认展开全部
  (function init() {{
    // caret 初始向下
    document.querySelectorAll(".caret").forEach(c => c.style.transform = "rotate(45deg)");
    refreshGroupCounts();
  }})();
</script>
</body>
</html>
"""


def run_inspection(
    *,
    enable_prom: bool = True,
    include: Optional[Sequence[str]] = None,
    per_check_timeout_seconds: int = 5,
    total_timeout_seconds: int = 25,
    max_workers: int = 6,
    save_report: bool = True,
) -> Dict[str, object]:
    t0_all = time.time()
    run_id = _safe_run_id()

    include_set = set([x.strip().lower() for x in (include or []) if str(x or "").strip()])

    def want(group: str) -> bool:
        if not include_set:
            return True
        return group.lower() in include_set

    tasks: List[tuple[str, Callable[[], InspectItem]]] = []

    if want("prom"):
        tasks.append(("prom", lambda: checks.check_prometheus_basic(enable=enable_prom)))
    if want("nodes"):
        tasks.append(("nodes", checks.check_nodes_ready))
    if want("system"):
        tasks.append(("system", checks.check_kube_system_core_pods))
    if want("pods"):
        tasks.append(("pods", checks.check_pods_abnormal))
    if want("events"):
        tasks.append(("events", checks.check_events_warnings))
    if want("storage"):
        tasks.append(("storage", checks.check_storage_basic))
    if want("dns"):
        tasks.append(("dns", checks.check_kube_dns_endpoints))

    items: List[InspectItem] = []
    summary = InspectSummary()
    deadline = time.time() + max(1, int(total_timeout_seconds))

    with ThreadPoolExecutor(max_workers=max(1, int(max_workers))) as ex:
        future_map = {ex.submit(fn): (group, fn) for group, fn in tasks}

        for fut in as_completed(future_map):
            if time.time() > deadline:
                for _f, (grp, _fn) in future_map.items():
                    if _f.done():
                        continue
                    items.append(
                        InspectItem(
                            key=f"timeout_{grp}",
                            title=f"巡检超时：{grp}",
                            level="error",
                            detail=f"总超时 {total_timeout_seconds}s，部分巡检项未完成",
                            suggestion="降低 include 范围或增加 total_timeout_seconds。",
                            durationMs=0,
                        )
                    )
                    summary.add("error")
                break

            group, _fn = future_map[fut]
            try:
                it = fut.result(timeout=max(1, int(per_check_timeout_seconds)))
            except FuturesTimeout:
                it = InspectItem(
                    key=f"timeout_{group}",
                    title=f"巡检超时：{group}",
                    level="error",
                    detail=f"单项超时 {per_check_timeout_seconds}s",
                    suggestion="检查集群 API 响应是否变慢，或调大 per_check_timeout_seconds。",
                    durationMs=per_check_timeout_seconds * 1000,
                )
            except Exception as e:
                it = InspectItem(
                    key=f"failed_{group}",
                    title=f"巡检异常：{group}",
                    level="error",
                    detail=f"执行异常：{e}",
                    durationMs=0,
                )

            items.append(it)
            summary.add(it.level)

    duration_ms = int((time.time() - t0_all) * 1000)

    report = InspectReport(
        runId=run_id,
        updatedAt=_now_iso(),
        durationMs=duration_ms,
        summary=summary,
        items=sorted(items, key=lambda x: (_level_rank(x.level), x.key)),
        meta={
            "enablePrometheus": bool(enable_prom),
            "include": list(include_set) if include_set else [],
            "perCheckTimeoutSeconds": int(per_check_timeout_seconds),
            "totalTimeoutSeconds": int(total_timeout_seconds),
        },
    )

    html = render_html(report)

    paths: Dict[str, str] = {}
    if save_report:
        base = Path("data") / "reports"
        base.mkdir(parents=True, exist_ok=True)

        html_path = base / f"{run_id}.html"
        json_path = base / f"{run_id}.json"

        html_path.write_text(html, encoding="utf-8")

        # ✅ Pydantic v2：用 model_dump + json.dumps 控制 ensure_ascii
        json_text = json.dumps(report.model_dump(), ensure_ascii=False, indent=2)
        json_path.write_text(json_text, encoding="utf-8")

        paths = {"html": str(html_path), "json": str(json_path)}

    return {"report": report, "html": html, "paths": paths}
