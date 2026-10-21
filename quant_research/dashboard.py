"""Offline, portable sector reports with auditable raw indicator rankings.

Every HTML file embeds its inputs and works from ``file://`` without a server.
Sorting is a viewing operation; it never changes portfolio targets or results.
"""

from dataclasses import asdict
from datetime import date, datetime
import html
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

from hkquant.registry import FACTOR_SPECS
from . import __version__


GROUPS = {
    "summary": ("综合指标", "Summary"), "momentum": ("动量", "Momentum"),
    "reversal": ("反转", "Reversal"), "risk": ("风险", "Risk"),
    "liquidity": ("量价与流动性", "Volume & liquidity"),
    "value": ("估值", "Value"), "quality": ("质量", "Quality"),
    "growth": ("成长", "Growth"),
}

SUMMARY_METRICS = [
    {"id": "score", "label": "综合得分", "label_en": "Composite score", "direction": 1},
    {"id": "rolling_mean_percentile", "label": "连续月平均排名百分位", "label_en": "Trailing mean rank percentile", "direction": -1},
    {"id": "rank", "label": "全样本本月名次", "label_en": "Universe monthly rank", "direction": -1},
    {"id": "rolling_rank", "label": "全样本连续月名次", "label_en": "Universe trailing rank", "direction": -1},
    *[{"id": f"group_score_{group}", "label": f"{label[0]}得分", "label_en": f"{label[1]} score", "direction": 1}
      for group, label in GROUPS.items() if group in ("momentum", "reversal", "risk", "liquidity")],
]


def _safe(value):
    """Strict JSON values, converting all non-finite numerical inputs to null."""
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_safe(item) for item in value]
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value) if np.isfinite(value) else None
    return str(value)


def _json(value):
    return json.dumps(_safe(value), ensure_ascii=False, allow_nan=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _snapshot(frame, label):
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{label} must be a DataFrame")
    if frame.empty:
        return {}
    if "ticker" not in frame or frame.ticker.duplicated().any():
        raise ValueError(f"{label} requires one snapshot row per ticker")
    return {str(row["ticker"]): row for row in frame.to_dict("records")}


def _payload(latest, factors, sectors, manifest):
    if len(sectors) != 11 or len({s["id"] for s in sectors}) != 11:
        raise ValueError("Dashboard requires exactly 11 unique sectors")
    for sector in sectors:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", sector["id"]):
            raise ValueError("Sector id must be a safe filename component")
    ranking = _snapshot(latest, "latest")
    values = _snapshot(factors, "factors")
    rows, seen = [], set()
    for sector in sectors:
        for stock in sector["stocks"]:
            ticker = stock["ticker"]
            if ticker in seen:
                raise ValueError(f"Duplicate sector stock: {ticker}")
            seen.add(ticker)
            current, factor = ranking.get(ticker, {}), values.get(ticker, {})
            if (current.get("date") is not None and factor.get("date") is not None
                    and pd.Timestamp(current["date"]) != pd.Timestamp(factor["date"])):
                raise ValueError(f"Ranking and factor snapshot dates differ for {ticker}")
            row = {"ticker": ticker, "name": stock.get("name", ticker), "sector": sector["id"],
                   "date": factor.get("date", current.get("date")),
                   "reason": current.get("reason", "missing_snapshot"),
                   "rolling_reason": current.get("rolling_reason", "missing_snapshot")}
            for metric in SUMMARY_METRICS:
                row[metric["id"]] = current.get(metric["id"])
            for spec in FACTOR_SPECS:
                row[spec.id] = factor.get(spec.id) if spec.status == "implemented" else None
            rows.append(row)
    definitions = [dict(metric, group="summary", status="implemented", formula="monthly cross-sectional ranking; universe membership as configured", min_observations=0)
                   for metric in SUMMARY_METRICS]
    definitions += [dict(asdict(spec), label_en=spec.id.replace("_", " ")) for spec in FACTOR_SPECS]
    return _safe({"version": __version__, "manifest": manifest, "sectors": sectors,
                  "definitions": definitions, "rows": rows})


CSS = r"""
:root{font-family:Inter,'Segoe UI','Microsoft YaHei',sans-serif;color:#173145;background:#f2f6fa;font-size:14px;--blue:#1267ce;--border:#dce5ee;--muted:#657b8b;--ink:#173145}*{box-sizing:border-box}body{margin:0}a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}button,select,input{font:inherit}button,select,input{border:1px solid #cbd9e5;border-radius:7px;background:white;padding:9px 12px;color:var(--ink)}button{cursor:pointer}button:hover{background:#eef5ff}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #72aaf1;outline-offset:2px}.shell{display:grid;grid-template-columns:230px minmax(0,1fr);min-height:100vh}aside{background:#112d43;color:#d8e8f4;padding:28px 16px;position:sticky;top:0;height:100vh;overflow:auto}.brand{font-size:17px;font-weight:750;padding:0 10px}.brand small{display:block;font-size:11px;font-weight:500;letter-spacing:2px;margin-top:8px;color:#9cbbd1}.nav-label{font-size:11px;letter-spacing:1px;color:#91b1c9;padding:28px 10px 10px}nav a{display:flex;justify-content:space-between;gap:10px;color:#d8e8f4;padding:10px;border-radius:7px;margin:3px 0;font-size:13px}nav a:hover{background:#1b405c;text-decoration:none}nav a.active{background:#2469a2;color:white}nav a span{opacity:.65;font-size:11px}.aside-footer{font-size:11px;color:#9bb8cc;line-height:1.8;border-top:1px solid #315166;padding:20px 10px;margin-top:24px}main{padding:28px 34px 48px;min-width:0;max-width:1800px;width:100%;margin:auto}.topline{display:flex;align-items:center;justify-content:space-between;gap:15px;margin-bottom:22px}.eyebrow{letter-spacing:1.8px;color:#617e94;font-size:11px;font-weight:700}.lang{font-size:12px;border:1px solid var(--border);padding:7px 12px;border-radius:20px;background:white}h1{font-size:30px;letter-spacing:-.8px;margin:8px 0 10px;line-height:1.25}h2{font-size:16px;margin:0 0 8px}p{line-height:1.7;margin:8px 0}.subtitle{color:var(--muted);font-size:13px;max-width:1050px}.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:24px 0}.card{background:white;border:1px solid var(--border);border-radius:10px;padding:18px}.card label{display:block;color:var(--muted);font-size:12px;margin-bottom:9px}.card strong{font-size:24px;font-weight:650}.card .small{font-size:17px}.card small{display:block;color:#7890a1;font-size:11px;margin-top:7px}.note{padding:12px 16px;border-left:3px solid #379589;background:#eaf6f3;border-radius:0 6px 6px 0;font-size:12px;line-height:1.7;margin:18px 0}.note.warning{border-color:#d89d38;background:#fff5df}.panel{background:white;border:1px solid var(--border);border-radius:11px;margin:20px 0;overflow:hidden}.panel-head{padding:20px 22px 16px;border-bottom:1px solid var(--border)}.controls{display:flex;flex-wrap:wrap;gap:12px;align-items:end;padding:18px 22px 12px}.control{display:flex;flex-direction:column;gap:6px;min-width:140px}.control.metric{flex:1;min-width:260px}.control label{font-size:11px;font-weight:600;color:var(--muted)}.control select,.control input{width:100%}.tabs{display:flex;flex-wrap:wrap;gap:6px;padding:4px 22px 14px}.tab{padding:6px 10px;font-size:12px;border-color:transparent;background:#f2f5f9;color:#516d84}.tab.active{background:#e4efff;color:#135da8;border-color:#b9d5fa}.metric-description{padding:0 22px 14px;line-height:1.8;font-size:12px;color:#60788c;overflow-wrap:anywhere}.metric-description code{font-size:11px;color:#385c76;background:#f4f7fa;padding:2px 5px}.table-scroll{overflow:auto;max-height:580px;position:relative}table{border-collapse:separate;border-spacing:0;min-width:100%;font-variant-numeric:tabular-nums}th,td{text-align:right;padding:12px 14px;border-bottom:1px solid #edf1f6;white-space:nowrap;font-size:12px}th{position:sticky;top:0;background:#f5f8fc;z-index:2;color:#55718a;font-weight:600;max-width:215px;white-space:normal;min-width:140px;vertical-align:bottom}th:first-child,td:first-child{text-align:center;min-width:60px;width:60px}th:nth-child(2),td:nth-child(2){text-align:left;position:sticky;left:0;background:#fff;z-index:1;min-width:165px;border-right:1px solid #e3ebf3}th:nth-child(2){z-index:3;background:#f5f8fc}th button{padding:0;border:none;background:none;border-radius:0;color:inherit;font-weight:600;cursor:pointer;font-size:11px;width:100%;text-align:right;line-height:1.5}th button:hover{color:#1267ce;background:transparent}tbody tr:hover td{background:#f4f9ff}td.selected,th.selected{background:#edf5ff;color:#155d9b}td .ticker{font-weight:750;color:#183e5b;font-size:13px}td .company{display:block;font-size:10px;color:#7a8e9e;max-width:150px;overflow:hidden;text-overflow:ellipsis;margin-top:4px}.missing{color:#a5b3bf}.rank-chip{background:#edf5fd;border-radius:5px;display:inline-block;min-width:24px;padding:4px;color:#356b9d}.table-footer{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:12px 22px;color:#71889a;font-size:11px;border-top:1px solid var(--border)}.resources{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}.resources a{border:1px solid #c9d9e8;border-radius:7px;padding:9px 12px;background:#fff;font-size:12px}.metadata{display:grid;grid-template-columns:1fr 1fr;gap:18px}.metadata section{padding:20px 22px}.metadata dl{font-size:12px;display:grid;grid-template-columns:145px minmax(0,1fr);gap:9px;margin:14px 0 0}.metadata dt{color:#7890a1}.metadata dd{margin:0;overflow-wrap:anywhere}.metadata ul{padding-left:18px;font-size:12px;color:#617b8f;line-height:1.8}details{margin:12px 0;font-size:12px}summary{cursor:pointer;color:#335c79}pre{white-space:pre-wrap;word-break:break-word;background:#f5f8fc;padding:14px;border-radius:7px;font-size:11px;max-height:320px;overflow:auto}.definitions th,.definitions td{text-align:left;white-space:normal;min-width:150px}.definitions td:nth-child(2){position:static}.definitions td:first-child{font-family:monospace;min-width:200px;text-align:left}.foot{color:#8aa0b2;font-size:11px;text-align:center;padding-top:12px}.empty{padding:36px;text-align:center;color:#7e94a5}.status{font-weight:650;color:#26806f;font-size:12px}.badge{padding:4px 8px;border-radius:4px;background:#eaf2fb;color:#356d9b;font-size:11px}.print-button{font-size:12px;padding:7px 12px}.noscript{background:#fff5df;padding:20px}.section-skip{position:absolute;left:-9999px}.section-skip:focus{left:250px;top:5px;background:white;padding:10px;z-index:5}@media(max-width:1050px){.shell{grid-template-columns:190px minmax(0,1fr)}main{padding:22px}.cards{grid-template-columns:repeat(2,1fr)}.metadata{grid-template-columns:1fr}}@media(max-width:650px){.shell{display:block}aside{position:static;height:auto;padding:14px}aside nav{display:flex;overflow:auto}nav a{min-width:130px}.nav-label,.aside-footer{display:none}.brand small{display:inline;margin-left:12px}main{padding:18px 12px}h1{font-size:25px}.topline{margin-bottom:12px}.cards{gap:8px}.card{padding:13px}.card strong{font-size:22px}.controls{padding:14px}.control{flex:1}.control.metric{min-width:100%}.tabs{padding:4px 14px 14px}.metadata dl{grid-template-columns:120px 1fr}}@media print{aside,.controls,.tabs,.lang,.print-button,.resources{display:none}.shell{display:block}main{padding:0;max-width:none}.table-scroll{max-height:none;overflow:visible}.cards{grid-template-columns:repeat(4,1fr)}.panel{break-inside:avoid}th{position:static}.foot{margin-top:20px}}
"""


CSS += """
.etf-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;padding:18px 22px}.etf-card{display:flex;flex-direction:column;gap:7px;border:1px solid #d7e4f0;border-radius:9px;padding:16px;background:#f8fbff;transition:background .15s}.etf-card:hover{background:#eaf3ff;text-decoration:none;border-color:#92bcec}.etf-card strong{font-size:19px;color:#155da4}.etf-card span{font-size:13px;color:#365973}.etf-card small{font-size:11px;color:#657e92}
"""


# Kept separate so the exact numerical sorting logic can be exercised in Node.
SORT_JS = r"""
function finite(value) { return typeof value === 'number' && Number.isFinite(value); }
function sortRows(rows, key, direction) {
  const sign = direction === 'asc' ? 1 : -1;
  return rows.slice().sort((a, b) => {
    const av = a[key], bv = b[key], af = finite(av), bf = finite(bv);
    if (af !== bf) return af ? -1 : 1;
    if (af && av !== bv) return (av < bv ? -1 : 1) * sign;
    return a.ticker < b.ticker ? -1 : a.ticker > b.ticker ? 1 : 0;
  });
}
function rankRows(rows, key, direction) {
  let previous, rank = null;
  return sortRows(rows, key, direction).map((row, index) => {
    if (!finite(row[key])) return {row, rank: null};
    if (index === 0 || row[key] !== previous) rank = index + 1;
    previous = row[key];
    return {row, rank};
  });
}
"""


JS = SORT_JS + r"""
(() => {
  'use strict';
  const data = JSON.parse(document.getElementById('report-data').textContent);
  const zh = document.documentElement.lang === 'zh-CN';
  const T = (a, b) => zh ? a : b;
  const sector = document.body.dataset.sector;
  const rows = sector ? data.rows.filter(row => row.sector === sector) : data.rows;
  const defs = data.definitions;
  const names = Object.fromEntries(defs.map(d => [d.id, d]));
  const groupNames = {summary:T('综合指标','Summary'),momentum:T('动量','Momentum'),reversal:T('反转','Reversal'),risk:T('风险','Risk'),liquidity:T('量价与流动性','Volume & liquidity'),value:T('估值','Value'),quality:T('质量','Quality'),growth:T('成长','Growth')};
  const label = d => zh ? d.label : d.label_en;
  const el = id => document.getElementById(id);
  let group = 'all', key = 'score', direction = 'desc';
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const format = v => !finite(v) ? '—' : new Intl.NumberFormat(zh ? 'zh-CN' : 'en-US', {maximumSignificantDigits:7}).format(v);
  function options() {
    const search = el('factor-search').value.trim().toLowerCase();
    const matching = defs.filter(d => (group === 'all' || d.group === group) && `${d.id} ${d.label} ${d.label_en}`.toLowerCase().includes(search));
    el('metric').innerHTML = matching.map(d => `<option value="${esc(d.id)}">${esc(label(d))}${d.status !== 'implemented' ? T(' · 待财报数据',' · awaiting data') : ''}</option>`).join('');
    if (!matching.some(d => d.id === key)) {
      key = matching[0]?.id || '';
      if (key) direction = names[key].direction === 1 ? 'desc' : 'asc';
    }
    el('metric').value = key; el('direction').value = direction;
    render();
  }
  function visibleColumns() {
    const search = el('factor-search').value.trim().toLowerCase();
    return defs.filter(d => (group === 'all' || d.group === group) && `${d.id} ${d.label} ${d.label_en}`.toLowerCase().includes(search));
  }
  function displayedRows() {
    const search = el('stock-search').value.trim().toLowerCase();
    // Rank the entire sector before filtering so a search never promotes a stock.
    return rankRows(rows, key, direction).filter(({row}) => `${row.ticker} ${row.name}`.toLowerCase().includes(search));
  }
  function render() {
    const columns = visibleColumns();
    const def = names[key];
    const selected = def ? [def, ...columns.filter(d => d.id !== key)] : columns;
    el('table-head').innerHTML = `<tr><th>${T('页内名次','Page rank')}</th><th>${T('股票','Stock')}</th>${selected.map(d => `<th class="${d.id === key ? 'selected' : ''}" aria-sort="${d.id === key ? (direction === 'asc' ? 'ascending' : 'descending') : 'none'}"><button type="button" data-key="${esc(d.id)}" title="${esc(d.id)}">${esc(label(d))}${d.id === key ? (direction === 'asc' ? ' ↑' : ' ↓') : ''}</button></th>`).join('')}</tr>`;
    const ranked = displayedRows();
    el('table-body').innerHTML = ranked.map(({row,rank}) => `<tr data-ticker="${esc(row.ticker)}"><td>${rank === null ? '<span class="missing">—</span>' : `<span class="rank-chip">${rank}</span>`}</td><td><span class="ticker">${esc(row.ticker)}</span><span class="company" title="${esc(row.name)}">${esc(row.name)}</span></td>${selected.map(d => `<td class="${d.id === key ? 'selected ' : ''}${finite(row[d.id]) ? '' : 'missing'}" data-value="${finite(row[d.id]) ? row[d.id] : ''}" title="${finite(row[d.id]) ? row[d.id] : (d.status !== 'implemented' ? T('等待按公告时间对齐的财报数据','Awaiting point-in-time fundamentals') : T('数据缺失或预热不足','Missing data or insufficient history'))}">${format(row[d.id])}</td>`).join('')}</tr>`).join('');
    el('empty').hidden = ranked.length > 0 && selected.length > 0;
    el('counts').textContent = T(`显示 ${ranked.length} / ${rows.length} 只股票 · ${columns.length} 个指标列`,`${ranked.length} / ${rows.length} stocks · ${columns.length} metric columns`);
    el('metric-description').innerHTML = def ? `<strong>${esc(label(def))}</strong> <code>${esc(def.id)}</code> · ${esc(groupNames[def.group])}<br>${T('公式','Formula')}: <code>${esc(def.formula)}</code> · ${T('研究默认方向','Research default')}: ${def.direction === 1 ? T('较高优先','higher first') : T('较低优先','lower first')} · ${def.status === 'implemented' ? T('已实现','Implemented') : T('等待历史可用财报，暂不排名','Awaiting point-in-time fundamentals; unranked')}` : T('没有匹配的指标。','No matching indicators.');
    el('table-head').querySelectorAll('button').forEach(button => button.addEventListener('click', () => {
      const next = button.dataset.key;
      direction = next === key ? (direction === 'asc' ? 'desc' : 'asc') : (names[next].direction === 1 ? 'desc' : 'asc');
      key = next; el('metric').value = key; el('direction').value = direction; render();
    }));
  }
  el('metric').addEventListener('change', () => { key = el('metric').value; direction = names[key].direction === 1 ? 'desc' : 'asc'; el('direction').value = direction; render(); });
  el('direction').addEventListener('change', () => {direction=el('direction').value;render();});
  el('stock-search').addEventListener('input', render);
  el('factor-search').addEventListener('input', options);
  document.querySelectorAll('[data-group]').forEach(button => button.addEventListener('click', () => {
    group = button.dataset.group;
    document.querySelectorAll('[data-group]').forEach(b => b.classList.toggle('active', b === button));
    options();
  }));
  el('export-csv').addEventListener('click', () => {
    const columns = defs.map(d => d.id);
    const cell = value => {
      let raw = String(value ?? '');
      if (typeof value === 'string' && /^[=+@-]/.test(raw)) raw = "'" + raw;
      return '"' + raw.replace(/"/g,'""') + '"';
    };
    const lines = [['page_rank','ticker','name','sector',...columns], ...displayedRows().map(({row,rank}) => [rank,row.ticker,row.name,row.sector,...columns.map(c => row[c])])];
    const blob = new Blob(['\uFEFF' + lines.map(line=>line.map(cell).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8;'});
    const link=document.createElement('a'); link.href=URL.createObjectURL(blob); link.download=`${sector||'all'}_${key||'metrics'}_${direction}.csv`; link.click(); setTimeout(()=>URL.revokeObjectURL(link.href),1000);
  });
  el('print').addEventListener('click', () => window.print());
  options();
  window.quantReport = {sortRows, rankRows, data, getState:()=>({key,direction,group,sector})};
})();
"""


def _render(data, language, sector, links):
    zh = language == "zh"
    tr = lambda a, b: a if zh else b
    e = lambda v: html.escape(str(v if v is not None else "—"), quote=True)
    prefix = "../" if sector else ""
    suffix = "zh" if zh else "en"
    current = sector["id"] if sector else ""
    title = (f'{current} · {sector["name_zh" if zh else "name_en"]} ' + tr("个股排名", "stock rankings")) if sector else tr("全行业研究总览", "Cross-sector research overview")
    subset = [row for row in data["rows"] if not sector or row["sector"] == current]
    manifest = data["manifest"]
    anchor = manifest.get("latest_month_anchor", manifest.get("signal_date", "—"))
    as_of = manifest.get("as_of", manifest.get("as_of_date", "—"))
    created = manifest.get("created_at_utc", manifest.get("run_started_at_utc", "—"))
    kind = manifest.get("data_kind", "")
    synthetic = "synthetic" in str(kind).lower() or "demo" in str(kind).lower()
    nav = [f'<a class="{"active" if not sector else ""}" href="{prefix}report_{suffix}.html">{tr("全部股票", "All stocks")}<span>{len(data["rows"])}</span></a>']
    for item in data["sectors"]:
        target = f'{"" if sector else "sectors/"}{item["id"]}_{suffix}.html'
        nav.append(f'<a class="{"active" if current == item["id"] else ""}" href="{target}">{e(item["name_zh" if zh else "name_en"])}<span>{e(item["id"])}</span></a>')
    explorer = ""
    if not sector:
        cards = ''.join(
            f'<a class="etf-card" href="sectors/{e(item["id"])}_{suffix}.html" '
            f'aria-label="{e(item["id"])}: {tr("查看个股排名", "View stock rankings")}">'
            f'<strong>{e(item["id"])}</strong><span>{e(item["name_zh" if zh else "name_en"])}</span>'
            f'<small>{len(item["stocks"])} {tr("只研究样本股票 · 查看排名 →", "sample stocks · View rankings →")}</small></a>'
            for item in data["sectors"])
        explorer = (f'<section class="panel etf-explorer" id="sector-etfs"><div class="panel-head">'
                    f'<h2>{tr("按行业 ETF 查看个股排名", "Explore stocks by sector ETF")}</h2>'
                    f'<p class="subtitle">{tr("点击 ETF 代码进入对应行业的个股排名。每页展示已配置的研究样本，并非 ETF 的完整或历史持仓。", "Select an ETF to open stock rankings for its sector. Each page covers the configured research sample, not the fund’s complete or historical holdings.")}</p>'
                    f'</div><div class="etf-grid">{cards}</div></section>')
    other = f'{current}_{"en" if zh else "zh"}.html' if sector else f'report_{"en" if zh else "zh"}.html'
    resource_links = []
    link_names = {"etf": ("ETF 配置回测", "ETF allocation"), "stocks": ("个股策略回测", "Stock backtest"), "validation": ("稳健性与时间分离验证", "Robustness & time split")}
    for name, path in (links or {}).items():
        if isinstance(path, dict):
            path = path.get(language, path.get("zh-CN" if zh else "en"))
        if not path:
            continue
        path = str(path)
        if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", path) or path.startswith(("/", "\\")) or ".." in Path(path).parts:
            raise ValueError("Report resource links must be relative paths inside the report bundle")
        resource_links.append(f'<a href="{e(prefix + path)}">{e(tr(*link_names.get(name, (name, name))))} ↗</a>')
    resource_links += [f'<a href="{prefix}latest_factors.csv" download>{tr("全部指标 CSV", "All indicators CSV")} ↓</a>', f'<a href="{prefix}dashboard_data.json" download>{tr("报告数据 JSON", "Report data JSON")} ↓</a>']
    definitions = []
    for spec in data["definitions"]:
        if spec["group"] == "summary":
            continue
        definitions.append(f'<tr><td>{e(spec["id"])}</td><td>{e(spec["label"] if zh else spec["label_en"])}</td><td>{e(tr(*GROUPS[spec["group"]]))}</td><td>{e(spec["formula"])}</td><td>{tr("较高优先", "Higher first") if spec["direction"] == 1 else tr("较低优先", "Lower first")}</td><td>{tr("已实现", "Implemented") if spec["status"] == "implemented" else tr("等待历史可用财报", "Awaiting PIT fundamentals")}</td></tr>')
    tabs = '<button type="button" class="tab active" data-group="all">' + tr("全部 100 项 + 综合", "All 100 + summary") + '</button>'
    tabs += ''.join(f'<button type="button" class="tab" data-group="{key}">{e(tr(*label))}</button>' for key, label in GROUPS.items())
    warning = f'<div class="note warning">{tr("合成数据演示：用于核验功能和界面，不能视为真实市场表现。", "SYNTHETIC DEMO: verifies software and presentation only; not market performance.")}</div>' if synthetic else ''
    failures = manifest.get("errors") or manifest.get("failures") or manifest.get("module_errors")
    if not failures and manifest.get("status") in ("partial_failure", "failed"):
        failures = manifest.get("validation_summary") or manifest.get("error") or manifest["status"]
    if failures:
        warning += f'<div class="note warning">{tr("部分模块未完成，请查看运行记录：", "Some modules did not complete. See run details: ")}{e(json.dumps(failures, ensure_ascii=False))}</div>'
    body = f'''<!doctype html>
<html lang="{"zh-CN" if zh else "en"}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)} · Quant Research Lab v{e(data["version"])}</title><style>{CSS}</style></head>
<body data-sector="{e(current)}"><a class="section-skip" href="#ranking">{tr("跳到排名", "Skip to rankings")}</a><div class="shell"><aside><div class="brand">Quant Research Lab<small>MONTHLY / v{e(data["version"])}</small></div><div class="nav-label">{tr("11 个行业 · 个股研究", "11 SECTORS · EQUITY RESEARCH")}</div><nav>{''.join(nav)}</nav><div class="aside-footer">{tr("月度信号 · 日度记账", "Monthly signals · Daily accounting")}<br>{tr("本地报告，可离线浏览", "Portable, offline reports")}<br>{tr("固定研究样本", "Fixed research universe")}</div></aside>
<main><div class="topline"><span class="eyebrow">RESEARCH WORKSPACE / {e(current or 'UNIVERSE')}</span><div><button type="button" class="print-button" id="print">{tr("打印 / PDF", "Print / PDF")}</button> <a class="lang" href="{other}">{tr("English", "中文")}</a></div></div>
<h1>{e(title)}</h1><p class="subtitle">{tr("逐项查看因子数值，按任意指标升序或降序比较股票。排名仅反映当前页面的研究样本，不代表投资建议；更改显示顺序不会改变回测策略。", "Inspect every factor and rank stocks by any indicator in either direction. Ranks describe the research sample on this page, not investment recommendations. Display sorting does not change the backtest strategy.")}</p>
<div class="cards"><div class="card"><label>{tr("本页个股", "Stocks on this page")}</label><strong>{len(subset)}</strong><small>{tr("固定样本，非行业全部股票", "Fixed sample, not the entire sector")}</small></div><div class="card"><label>{tr("指标目录", "Indicator catalogue")}</label><strong>100</strong><small>{tr("65 已实现 · 35 等待财报", "65 implemented · 35 awaiting fundamentals")}</small></div><div class="card"><label>{tr("月度信号日期", "Monthly signal date")}</label><strong class="small">{e(anchor)}</strong><small>{tr("只使用已完成月份", "Completed calendar months only")}</small></div><div class="card"><label>{tr("本次研究截止", "Research cutoff")}</label><strong class="small">{e(as_of)}</strong><small>{tr("每次更新按运行时日期重算", "Recomputed at each refresh")}</small></div></div>
{explorer}{warning}<div class="note">{tr("全部 100 项指标均可选择。35 项财务指标暂缺按公告时间对齐的历史财报，显示「—」且不参与排名。缺失值始终排末尾；相同数值并列名次，再按股票代码稳定排序。行业页的综合得分沿用全样本评分，页内名次在本行业重新计算。", "All 100 indicators are selectable. The 35 financial indicators await historical fundamentals aligned to publication time; they display — and receive no rank. Missing values stay last; equal values share a rank, with ticker as a stable tie-breaker. Sector pages reuse universe composite scores and recalculate display ranks within the sector.")}</div>
<section class="panel" id="ranking"><div class="panel-head"><h2>{tr("个股指标与排名", "Stock indicators & rankings")}</h2><p class="subtitle">{tr("横向滚动查看全部指标；点击列标题切换排序。选中的指标固定显示在股票名称之后。", "Scroll horizontally for all indicators. Click a column header to sort; the selected indicator appears beside the stock name.")}</p></div><div class="controls"><div class="control metric"><label for="metric">{tr("排名指标", "Rank by indicator")}</label><select id="metric"></select></div><div class="control"><label for="direction">{tr("排名方向", "Sort direction")}</label><select id="direction"><option value="desc">{tr("降序 · 从大到小", "Descending · high to low")}</option><option value="asc">{tr("升序 · 从小到大", "Ascending · low to high")}</option></select></div><div class="control"><label for="stock-search">{tr("查找股票", "Find stock")}</label><input id="stock-search" placeholder="{tr("代码 / 名称", "Ticker / company")}" type="search"></div><div class="control"><label for="factor-search">{tr("查找指标", "Find indicator")}</label><input id="factor-search" placeholder="{tr("名称 / 指标 ID", "Name / indicator ID")}" type="search"></div><button id="export-csv" type="button">{tr("导出当前排名 ↓", "Export current ranks ↓")}</button></div><div class="tabs" role="group" aria-label="{tr("指标类别", "Indicator groups")}">{tabs}</div><div class="metric-description" id="metric-description"></div><div class="table-scroll"><table aria-label="{tr("可排序股票指标", "Sortable stock indicators")}"><thead id="table-head"></thead><tbody id="table-body"></tbody></table><div class="empty" id="empty" hidden>{tr("没有匹配的股票或指标。", "No matching stocks or indicators.")}</div></div><div class="table-footer"><span id="counts"></span><span>{tr("搜索不会改变原始页内名次 · 横向滚动 →", "Search preserves page ranks · Scroll horizontally →")}</span></div></section>
<noscript><p class="noscript">{tr("交互排名需要启用 JavaScript。仍可使用下方 CSV、JSON 文件查看全部指标。", "Enable JavaScript for interactive ranking. CSV and JSON downloads below contain every indicator.")}</p></noscript>
<div class="metadata"><section class="panel"><h2>{tr("研究报告与下载", "Research reports & downloads")}</h2><p class="subtitle">{tr("同一次运行生成的结果与验证记录。", "Results and validation from this run.")}</p><div class="resources">{''.join(resource_links)}</div><dl><dt>{tr("运行生成时间 UTC", "Created at UTC")}</dt><dd>{e(created)}</dd><dt>{tr("数据类型", "Data type")}</dt><dd>{e(kind)}</dd><dt>{tr("股票池性质", "Universe")}</dt><dd>{tr("固定样本；非历史指数成分股", "Fixed sample; not historical index constituents")}</dd></dl></section><section class="panel"><h2>{tr("阅读规则", "Interpretation")}</h2><ul><li>{tr("指标原值排序与组合选股规则分别展示，不自动寻找最优参数。", "Raw indicator ordering is separate from portfolio selection; no automatic search for optimal parameters.")}</li><li>{tr("行业分类是当前研究配置，不能证明历史分类或成分。", "Sector labels are the current research configuration, not evidence of historical classifications or membership.")}</li><li>{tr("时间分离报告不自动等于未见数据验证；请结合验证报告中的说明。", "A chronological split does not automatically establish unseen-data validation; read the validation report.")}</li></ul><details><summary>{tr("查看运行记录", "Inspect run metadata")}</summary><pre>{e(json.dumps(manifest, ensure_ascii=not zh, indent=2))}</pre></details></section></div>
<details class="panel"><summary class="panel-head">{tr("全部 100 项指标定义、公式与状态", "All 100 indicator definitions, formulas & status")}</summary><div class="table-scroll"><table class="definitions"><thead><tr><th>ID</th><th>{tr("名称", "Name")}</th><th>{tr("类别", "Group")}</th><th>{tr("公式", "Formula")}</th><th>{tr("默认方向", "Default direction")}</th><th>{tr("状态", "Status")}</th></tr></thead><tbody>{''.join(definitions)}</tbody></table></div></details><div class="foot">ChungKit WAN · LangCheng LI · XinQuan LIU · RunAng CAO<br>Quant Research Lab v{e(data["version"])} · {tr("月度研究报告", "Monthly research report")}</div>
</main></div><script type="application/json" id="report-data">{_json(data)}</script><script>{JS}</script></body></html>'''
    return body


def export_dashboard(output, *, latest, factors, sectors, manifest, links=None):
    """Write a bilingual overview and eleven bilingual sector pages.

    ``latest`` and ``factors`` contain at most one row per ticker at the same
    signal snapshot. Stocks configured without a row remain visible as missing.
    ``links`` values are paths relative to output, or ``{zh: path, en: path}``.
    """
    output = Path(output)
    data = _payload(latest, factors, sectors, manifest)
    output.mkdir(parents=True, exist_ok=True)
    sector_dir = output / "sectors"
    sector_dir.mkdir(exist_ok=True)
    (output / "dashboard_data.json").write_text(json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
    pd.DataFrame(data["rows"]).to_csv(output / "latest_factors.csv", index=False, encoding="utf-8-sig")
    for language in ("en", "zh"):
        (output / f"report_{language}.html").write_text(_render(data, language, None, links), encoding="utf-8")
        for sector in sectors:
            (sector_dir / f'{sector["id"]}_{language}.html').write_text(_render(data, language, sector, links), encoding="utf-8")
    (output / "report.html").write_text(_render(data, "en", None, links), encoding="utf-8")
    return output / "report.html"
