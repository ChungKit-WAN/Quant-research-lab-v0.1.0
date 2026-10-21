"""Portable, self-contained research reports with explicit data provenance."""

import hashlib
import html
import json
import platform
import re
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd

from . import __version__
from .report_text import CONFIG_FIELDS, GROUPS, LIMITATIONS, PERIODS, SOURCES, STRATEGIES


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def _json(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)


REPORT_FILES = {"en": "report_en.html", "zh-CN": "report_zh.html"}
TEAM_NAMES = ("ChungKit WAN", "LangCheng LI", "XinQuan LIU", "RunAng CAO")

PERFORMANCE_FIELDS = {
    "strategy": ("策略", "Strategy"), "period": ("区间", "Period"),
    "first_session": ("首个交易日", "First session"), "last_session": ("末个交易日", "Last session"),
    "observations": ("交易日数", "Trading sessions"), "opening_nav": ("期初净值", "Opening NAV"),
    "closing_nav": ("期末净值", "Closing NAV"), "net_total_return": ("扣费后总收益", "Net total return"),
    "net_cagr": ("扣费后年化复合收益率", "Net CAGR"),
    "annualized_volatility": ("年化波动率", "Annualized volatility"),
    "maximum_drawdown": ("最大回撤", "Maximum drawdown"),
    "daily_loss_cvar_95": ("日损失 CVaR 95", "Daily loss CVaR 95"),
    "tail_observation_mass": ("尾部观测概率质量", "Tail observation mass"),
    "buy_notional": ("买入名义额", "Buy notional"), "sell_notional": ("卖出名义额", "Sell notional"),
    "traded_notional": ("买卖名义额合计", "Total traded notional"),
    "transaction_costs": ("交易费用合计", "Total transaction costs"),
    "traded_notional_over_opening_nav": ("买卖额／期初净值", "Traded notional / opening NAV"),
    "transaction_costs_over_opening_nav": ("费用／期初净值", "Costs / opening NAV"),
    "rebalance_count": ("调仓次数", "Rebalances"),
}
WEIGHT_FIELDS = {
    "dates": ("起止日期", "Dates"), "ticker": ("资产代码", "Asset"),
    "first_close": ("首日收盘权重", "First closing weight"),
    "last_close": ("末日收盘权重", "Last closing weight"),
    "mean_close": ("平均收盘权重", "Mean closing weight"),
    "minimum_close": ("最低收盘权重", "Minimum closing weight"),
    "maximum_close": ("最高收盘权重", "Maximum closing weight"),
}
TECHNICAL_FIELDS = {"schema_version", "input_sha256", "implementation_sha256", "ledger_consistency_verified"}
PERCENT_FIELDS = {"net_total_return", "net_cagr", "annualized_volatility", "maximum_drawdown",
                  "daily_loss_cvar_95", "transaction_costs_over_opening_nav",
                  "first_close", "last_close", "mean_close", "minimum_close", "maximum_close"}

SORT_SCRIPT = '''<script>
document.querySelectorAll('table[data-sortable]').forEach(table => {
  table.querySelectorAll('thead button').forEach((button, column) => {
    button.addEventListener('click', () => {
      const heading = button.parentElement;
      const ascending = heading.getAttribute('aria-sort') !== 'ascending';
      const rows = Array.from(table.tBodies[0].rows);
      const values = rows.map(row => row.cells[column].dataset.sortValue ?? '');
      const numeric = values.filter(value => value !== '').every(value => Number.isFinite(Number(value)));
      rows.map((row, original) => ({row, original})).sort((left, right) => {
        const a = left.row.cells[column].dataset.sortValue ?? '';
        const b = right.row.cells[column].dataset.sortValue ?? '';
        if (a === '' || b === '') return a === b ? left.original - right.original : a === '' ? 1 : -1;
        const order = numeric ? Number(a) - Number(b) : a.localeCompare(b);
        return order === 0 ? left.original - right.original : ascending ? order : -order;
      }).forEach(item => table.tBodies[0].appendChild(item.row));
      table.querySelectorAll('thead th').forEach(th => th.setAttribute('aria-sort', 'none'));
      heading.setAttribute('aria-sort', ascending ? 'ascending' : 'descending');
    });
  });
});
</script>'''


def _text(zh, en, language):
    return html.escape(str(zh if language == "zh-CN" else en))


def _named(mapping, name, language):
    return _text(*mapping.get(name, (name, name)), language)


def _configuration(result, language):
    rows = []
    fields = dict(result["config"])
    fields.update({key: result.get("factor_config", {})[key]
                   for key in ("top_n", "ranking_window", "implemented_factor_count", "group_weights")
                   if key in result.get("factor_config", {})})
    for key, value in fields.items():
        label = _named(CONFIG_FIELDS, key, language)
        if key == "group_weights":
            display = "<br>".join(f'{_named(GROUPS, group, language)} {weight:.1%}' for group, weight in value.items())
        elif key == "max_weight":
            display = f"{value:.1%}"
        else:
            display = html.escape(", ".join(map(str, value)) if isinstance(value, (list, tuple)) else str(value))
        rows.append(f"<tr><th>{label}</th><td>{display}</td></tr>")
    return '<table class="config"><tbody>' + "".join(rows) + "</tbody></table>"


def _metric_value(key, value, language):
    if value is None:
        return "—"
    if key == "strategy":
        return _named(STRATEGIES, value, language)
    if key == "period":
        return _named(PERIODS, value, language)
    if key in PERCENT_FIELDS:
        return f"{value:.4%}"
    if isinstance(value, (float, np.floating)):
        return f"{value:.10g}"
    return html.escape(str(value))


def _sortable_table(rows, columns, labels, language, table_id, sector_links=None):
    headers = "".join(
        f'<th scope="col" data-field="{html.escape(key, quote=True)}" aria-sort="none">'
        f'<button type="button">{_named(labels, key, language)}</button></th>'
        for key in columns)
    rendered = []
    for row in rows:
        cells = []
        for key in columns:
            value = row.get(key)
            # Sorting uses the unrounded numeric value; missing values stay last.
            raw = "" if value is None else str(value)
            display = _metric_value(key, value, language)
            if key == "ticker" and value in (sector_links or {}):
                target = sector_links[value]
                display = (f'<a class="etf-link" href="{html.escape(target["href"], quote=True)}" '
                           f'title="{_text("查看板块个股排名", "View sector stock rankings", language)}">'
                           f'{display} ↗</a>')
            cells.append(f'<td data-sort-value="{html.escape(raw, quote=True)}">'
                         f'{display}</td>')
        rendered.append("<tr>" + "".join(cells) + "</tr>")
    return (f'<div class="table"><table id="{table_id}" data-sortable><thead><tr>{headers}</tr></thead>'
            f'<tbody>{"".join(rendered)}</tbody></table></div>')


def _complete_performance(result, language, sector_links=None):
    def text(zh, en):
        return _text(zh, en, language)

    # Any future scalar performance field is visible automatically; fingerprints
    # and nested conventions are retained separately from the numeric table.
    columns = list(dict.fromkeys(key for row in result["metrics"] for key, value in row.items()
                                if key not in TECHNICAL_FIELDS and not isinstance(value, (dict, list, tuple))))
    weights, technical = [], []
    for row in result["metrics"]:
        for ticker, values in row.get("sector_weights", {}).items():
            weights.append({"strategy": row["strategy"], "period": row["period"],
                            "dates": f'{row["first_session"]} → {row["last_session"]}',
                            "ticker": ticker, **values})
        technical.append({"strategy": row["strategy"], "period": row["period"],
                          **{key: value for key, value in row.items()
                             if key not in columns and key != "sector_weights"}})
    weight_columns = list(dict.fromkeys(key for row in weights for key in row))
    return (f'<h2>{text("全部绩效指标", "All performance metrics")}</h2>'
            f'<p class="muted">{text("横向滚动查看全部指标。点击列标题可切换升序／降序；CSV 保留完整精度。净值、费用和交易名义额采用初始资本的记账单位。买卖额为买入加卖出，未减半、未年化。", "Scroll horizontally for all metrics. Click a column heading to switch ascending / descending order; CSV retains full precision. NAV, fees and trade notionals use the initial-capital accounting units. Traded notional is buys plus sells, neither halved nor annualized.")}</p>'
            + _sortable_table(result["metrics"], columns, PERFORMANCE_FIELDS, language, "all-performance")
            + f'<h2>{text("逐资产实际权重统计", "Actual weight statistics by asset")}</h2>'
            + f'<p class="muted">{text("统计各区间实际收盘权重，不是目标权重；均值按交易日等权平均。权重可能在调仓间漂移超过目标上限。", "Statistics use actual closing weights within each period, not target weights; means weight trading sessions equally. Weights may drift above the target cap between rebalances.")}</p>'
            + _sortable_table(weights, weight_columns, {**PERFORMANCE_FIELDS, **WEIGHT_FIELDS}, language, "asset-weight-statistics", sector_links)
            + f'<details><summary>{text("计算口径、版本与数据指纹（机器字段）", "Calculation conventions, versions and fingerprints (machine fields)")}</summary>'
            + f'<pre>{html.escape(_json(technical))}</pre></details>')


def _chart(result, language, drawdown=False):
    series = []
    for name, ledger in result["strategies"].items():
        values = np.asarray([ledger["initial_cash"], *[row["nav"] for row in ledger["daily"]]])
        values = (values / np.maximum.accumulate(values) - 1) * 100 if drawdown else values / values[0]
        series.append((name, values))
    lo = min(float(v.min()) for _, v in series)
    hi = max(float(v.max()) for _, v in series)
    if hi == lo:
        hi = lo + 1
    colours = ("#38bdf8", "#a78bfa", "#34d399")
    paths, legend = [], []
    for i, (name, values) in enumerate(series):
        points = " ".join(f"{65 + j / max(1, len(values)-1) * 790:.2f},{245-(v-lo)/(hi-lo)*205:.2f}"
                          for j, v in enumerate(values))
        colour = colours[i % len(colours)]
        paths.append(f'<polyline points="{points}" fill="none" stroke="{colour}" stroke-width="1.7"/>')
        legend.append(f'<span class="legend-item" style="color:{colour}">{_named(STRATEGIES, name, language)}</span>')
    first = next(iter(result["strategies"].values()))
    labels = (("回撤（%）", "Drawdown (%)") if drawdown else
              ("扣费后净值（初始 = 1）", "Net wealth after costs (initial = 1)"))
    label = _text(*labels, language)
    guides = []
    for fraction in (0, .5, 1):
        y = 245 - fraction * 205
        guides.append(f'<line x1="65" y1="{y}" x2="855" y2="{y}" stroke="#334155"/>'
                      f'<text x="8" y="{y+4}" fill="#94a3b8" font-size="12">{lo+fraction*(hi-lo):.2f}</text>')
    return (f'<h2>{label}</h2><div class="legend">{"".join(legend)}</div>'
            f'<svg viewBox="0 0 900 290" role="img" aria-label="{label}">'
            + "".join(guides + paths)
            + f'<text x="65" y="275" fill="#94a3b8">{first["baseline_session"]}</text>'
            + f'<text x="760" y="275" fill="#94a3b8">{first["daily"][-1]["session"]}</text></svg>')


def _sector_navigation(sector_links, language):
    """Expose the stock-ranking drill-down from both portfolio report families."""
    if not sector_links:
        return ""
    cards = "".join(
        f'<a class="sector-card" href="{html.escape(item["href"], quote=True)}">'
        f'<strong>{html.escape(ticker)}</strong><span>{html.escape(item["name"])}</span>'
        f'<small>{item["stock_count"]} {_text("只样本个股", "sample stocks", language)} →</small></a>'
        for ticker, item in sector_links.items())
    return (f'<section id="sector-stock-rankings"><h2>{_text("按 ETF 查看板块个股排名", "Explore stock rankings by ETF", language)}</h2>'
            f'<p class="muted">{_text("点击 ETF 代码，查看对应板块的个股排名，并按任意指标切换升序或降序。每个板块使用配置中的固定研究样本，不代表完整或历史 ETF 成分股。", "Click an ETF to open its sector stock rankings and sort any indicator in either direction. Each sector uses the configured research sample, not complete or historical ETF holdings.", language)}</p>'
            f'<nav class="sector-grid" aria-label="{_text("ETF 板块个股排名", "ETF sector stock rankings", language)}">{cards}</nav></section>')


def _render_report(result, bilingual_limits, source_label, language, dashboard_link=None, sector_links=None):
    """Render one language from the same computed ledger and metrics."""
    if language not in REPORT_FILES:
        raise ValueError("Unsupported report language")

    def text(zh, en):
        return _text(zh, en, language)

    def named(mapping, name):
        return _named(mapping, name, language)

    data_kind = result["data_kind"]
    first = next(iter(result["strategies"].values()))
    table = []
    for row in result["metrics"]:
        cells = [named(STRATEGIES, row["strategy"]), named(PERIODS, row["period"])]
        cells.extend(html.escape(str(value)) for value in (
            f'{row["first_session"]} → {row["last_session"]}', f'{row["net_cagr"]:.2%}',
            f'{row["annualized_volatility"]:.2%}', f'{row["maximum_drawdown"]:.2%}',
            f'{row["daily_loss_cvar_95"]:.2%}', row["rebalance_count"],
        ))
        table.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
    banner = (text("合成演示：不代表历史投资业绩", "SYNTHETIC DEMO: not historical investment performance")
              if data_kind == "synthetic_demo" else
              text("用户数据研究：行情尚未独立认证", "USER DATA RESEARCH: market data not independently verified"))
    source = (text(SOURCES[source_label], source_label) if source_label in SOURCES else html.escape(source_label))
    heading = text("月度策略，共用交易账本", "Monthly strategies, shared portfolio accounting")
    timing = text("月末信号 → 下一交易日收盘执行 → 日度净值", "Month-end signal → next-session close execution → daily net wealth")
    metric_note = text("CAGR 按每年 252 个交易日折算；CVaR 为最差 5% 日损失概率质量的均值。",
                        "CAGR is annualized using 252 trading sessions; CVaR is the mean of the worst 5% probability mass of daily losses.")
    headers = [("策略", "Strategy"), ("区间", "Period"), ("起止日期", "Dates"), ("扣费后年化复合收益率", "Net CAGR"),
               ("年化波动率", "Annualized volatility"), ("最大回撤", "Maximum drawdown"),
               ("日损失 CVaR 95", "Daily loss CVaR 95"), ("调仓次数", "Rebalances")]
    cards = [("资产数", "Assets", len(result["config"]["tickers"])),
             ("策略数", "Strategies", len(result["strategies"])),
             ("每策略调仓数", "Rebalances per strategy", first["rebalance_count"]),
             ("每策略净值记录", "Daily records per strategy", first["daily_rows"])]
    links = [("metrics.csv", "指标 CSV", "Metrics CSV"), ("target_weights.csv", "目标权重", "Target weights"),
             ("schedule.csv", "信号日程", "Signal schedule"), ("results.json", "完整账本", "Full ledger"),
             ("manifest.json", "复现清单", "Reproducibility manifest")]
    other_language = "en" if language == "zh-CN" else "zh-CN"
    dashboard_navigation = (f'<a href="{html.escape(dashboard_link, quote=True)}">'
                            f'{text("返回总览", "Back to overview")}</a> · ' if dashboard_link else "")
    document = f'''<!doctype html><html lang="{language}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{text("量化研究报告", "Quant Research Lab Report")} — v{__version__}</title><style>
body{{margin:0;background:#0b1220;color:#e2e8f0;font:15px/1.65 system-ui,sans-serif}}main{{max-width:1080px;margin:auto;padding:32px 24px}}
h1{{font-size:32px;margin:12px 0}}h2{{font-size:20px;margin:28px 0 8px}}.muted{{color:#94a3b8}}.banner{{padding:14px 18px;border:1px solid #fbbf24;color:#fcd34d;border-radius:8px}}
.cards{{display:flex;gap:16px;flex-wrap:wrap;margin:24px 0}}.card{{background:#172033;border-radius:10px;padding:18px;flex:1;min-width:150px}}.card b{{display:block;font-size:24px}}
svg{{width:100%;background:#111b2d;border-radius:10px;margin-top:12px}}.table{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{text-align:left;padding:10px;border-bottom:1px solid #334155;white-space:nowrap}}th{{color:#94a3b8}}.config td,.config th{{white-space:normal}}
li{{margin:14px 0}}code{{color:#7dd3fc}}a{{color:#7dd3fc}}.legend{{display:flex;gap:20px;flex-wrap:wrap;font-size:13px}}details{{margin-top:24px}}pre{{overflow:auto;background:#111b2d;padding:16px}}
.downloads{{display:flex;gap:20px;flex-wrap:wrap;margin:24px 0}}.source{{overflow-wrap:anywhere}}.language{{text-align:right}}footer{{margin-top:32px;border-top:1px solid #334155;padding-top:16px}}
.sector-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin:16px 0 28px}}.sector-card{{display:flex;flex-direction:column;gap:4px;background:#172033;border:1px solid #334155;border-radius:8px;padding:14px;text-decoration:none}}.sector-card:hover{{background:#1c3149;border-color:#7dd3fc}}.sector-card strong{{font-size:18px}}.sector-card span{{color:#e2e8f0;font-size:13px}}.sector-card small{{color:#94a3b8}}.sector-card:focus-visible,.etf-link:focus-visible{{outline:2px solid #7dd3fc;outline-offset:3px}}
th button{{font:inherit;color:inherit;background:none;border:0;padding:0;cursor:pointer;text-align:left}}th button:focus-visible{{outline:2px solid #7dd3fc;outline-offset:4px}}th[aria-sort="ascending"] button::after{{content:" ↑"}}th[aria-sort="descending"] button::after{{content:" ↓"}}
</style></head><body><main><nav class="language">{dashboard_navigation}<a href="{REPORT_FILES[other_language]}" hreflang="{other_language}">{text("英文版", "Chinese version")}</a></nav>
<div class="muted">QUANT RESEARCH LAB · v{__version__} · {text("月度", "MONTHLY")}</div>
<h1>{heading}</h1><p class="banner">{banner}</p>
<p class="muted">{timing}</p><div class="muted source">{text("数据来源", "Data source")}: {source}</div>
<div class="cards">{"".join(f'<div class="card">{text(zh, en)}<b>{value}</b></div>' for zh, en, value in cards)}</div>
{_sector_navigation(sector_links, language)}
{_chart(result, language)}{_chart(result, language, True)}<h2>{text("分期绩效指标", "Performance by period")}</h2><p class="muted">{metric_note}</p>
<div class="table"><table><thead><tr>{"".join(f'<th>{text(zh, en)}</th>' for zh, en in headers)}</tr></thead><tbody>{"".join(table)}</tbody></table></div>
{_complete_performance(result, language, sector_links)}
<h2>{text("研究边界与假设", "Research boundaries and assumptions")}</h2><ul>{"".join(f'<li>{text(item["zh"], item["en"])}</li>' for item in bilingual_limits)}</ul>
<h2>{text("实验参数", "Experiment configuration")}</h2>{_configuration(result, language)}
<details><summary>{text("原始机器可读参数（保留英文代码标识）", "Raw machine-readable parameters (code identifiers preserved)")}</summary><pre>{html.escape(_json({"config": result["config"], "factor_config": result.get("factor_config")}))}</pre></details>
<h2>{text("数据与复现文件", "Data and reproducibility files")}</h2>
<p class="muted">{text("中文与英文报告使用同一份计算结果；CSV／JSON 的代码字段保持英文，便于程序读取。", "The English and Chinese reports use the same computed results. CSV/JSON code fields remain in English for programmatic use.")}</p>
<nav class="downloads">{"".join(f'<a href="{file}">{text(zh, en)}</a>' for file, zh, en in links)}</nav>
<footer class="muted">{text("研发团队", "Research team")}: {" · ".join(TEAM_NAMES)}</footer></main>{SORT_SCRIPT}</body></html>'''
    return document


def _language_index(data_kind):
    """Keep report.html stable and open the primary English report by default."""
    notice = ("SYNTHETIC DEMO: not historical investment performance / 合成演示：不代表历史投资业绩"
              if data_kind == "synthetic_demo" else
              "USER DATA RESEARCH: market data not independently verified / 用户数据研究：行情尚未独立认证")
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="0;url=report_en.html">
<title>English report / 英文报告 — Quant Research Lab</title>
<style>body{{margin:0;background:#0b1220;color:#e2e8f0;font:16px/1.7 system-ui,sans-serif}}
main{{max-width:760px;margin:8vh auto;padding:28px}}h1{{font-size:30px}}
nav{{display:flex;gap:20px;flex-wrap:wrap;margin:28px 0}}a{{color:#7dd3fc;border:1px solid #334155;border-radius:10px;padding:20px 28px;text-decoration:none}}
.notice{{color:#fcd34d}}.muted{{color:#94a3b8}}</style></head><body><main>
<p class="muted">QUANT RESEARCH LAB · v{__version__}</p><h1>Opening the English report</h1>
<p class="notice">{notice}</p><nav><a href="report_en.html" lang="en" hreflang="en">English report →</a>
<a href="report_zh.html" lang="zh-CN" hreflang="zh-CN">中文辅助报告</a></nav>
<p lang="en">Both reports share the same computed results, chart data and reproducibility files.</p>
<p lang="zh-CN">默认使用英文；中文报告提供辅助阅读。两份报告共用同一份计算结果、图表数据及复现文件。</p>
</main></body></html>'''


def _report_navigation(output, language):
    """Link only to existing sibling dashboard pages; standalone exports stay portable."""
    dashboard_file = output.parent / "dashboard_data.json"
    overview = output.parent / REPORT_FILES[language]
    if not dashboard_file.is_file() or not overview.is_file():
        return None, {}
    data = json.loads(dashboard_file.read_text(encoding="utf-8"))
    suffix = "zh" if language == "zh-CN" else "en"
    sector_links = {}
    for sector in data.get("sectors", []):
        ticker = sector["id"]
        if not isinstance(ticker, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", ticker):
            raise ValueError("Sector id must be a safe filename component")
        relative = f"sectors/{ticker}_{suffix}.html"
        if (output.parent / relative).is_file():
            sector_links[ticker] = {"href": "../" + relative,
                                    "name": sector.get("name_zh" if suffix == "zh" else "name_en", ticker),
                                    "stock_count": len(sector.get("stocks", []))}
    return "../" + REPORT_FILES[language], sector_links


def export_report(result, output, *, data_kind, input_sha256, source_label, demo_csv=None):
    """Do not overwrite prior evidence; use an empty/new output directory."""
    output = Path(output)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Output must be a new or empty directory; choose a different --output")
    limitations = [
        "Monthly signals at close; execution at the next XNYS session close. New positions earn returns only after execution.",
        "Fixed selected universe; no historical membership or delisted-asset reconstruction. Selection and survivorship bias remain.",
        "Adjusted-price synthetic units, not an independently verified raw-share/dividend ledger. Do not add dividends twice.",
        "XNYS regular sessions are a calendar proxy; fractional units and zero cash interest are assumed.",
        "Costs apply to every buy/sell notional, including entry. Spread, market impact, volume limits, and partial fills are not modeled.",
        "Holdout is a date partition, not certification that results were unseen. No claim of statistical significance or predictive power.",
        "Annualization uses 252 sessions. Targets obey the cap; daily weights may drift above it. No forced terminal liquidation.",
    ]
    if data_kind == "synthetic_demo":
        limitations.insert(0, "SYNTHETIC DATA — pipeline demonstration only. These numbers are not historical investment performance.")
    else:
        limitations.insert(0, "User-supplied prices: data rights, adjustments and historical availability have not been independently verified.")
    limitations.extend(item for item in result.get("limitations", []) if item not in limitations)
    translation = {**LIMITATIONS, **result.get("limitations_zh", {})}
    missing = [item for item in limitations if item not in translation]
    if missing:
        raise ValueError("Chinese report translation required for additional limitations: " + "; ".join(missing))
    bilingual_limits = [{"zh": translation[item], "en": item} for item in limitations]
    output.mkdir(parents=True, exist_ok=True)
    if demo_csv is not None:
        (output / "demo_prices.csv").write_bytes(demo_csv)
    result["data_kind"] = data_kind
    result["limitations"] = limitations
    result["report_languages"] = list(REPORT_FILES)
    result["report_files"] = dict(REPORT_FILES)
    result["limitations_bilingual"] = bilingual_limits
    (output / "results.json").write_text(_json(result), encoding="utf-8")
    scalar_metrics = [{key: val for key, val in row.items() if not isinstance(val, (dict, list, tuple))}
                      for row in result["metrics"]]
    pd.DataFrame(scalar_metrics).to_csv(output / "metrics.csv", index=False)
    pd.DataFrame(result["schedule"]).to_csv(output / "schedule.csv", index=False)
    pd.DataFrame(result["target_weights"]).to_csv(output / "target_weights.csv", index=False)
    for name, ledger in result["strategies"].items():
        rows = [{key: val for key, val in row.items() if not isinstance(val, (dict, list))} for row in ledger["daily"]]
        pd.DataFrame(rows).to_csv(output / f"{name}_daily.csv", index=False)
    for language, filename in REPORT_FILES.items():
        # Standalone exports must not contain a dead parent-navigation link.
        dashboard_link, sector_links = _report_navigation(output, language)
        document = _render_report(result, bilingual_limits, source_label, language, dashboard_link, sector_links)
        (output / filename).write_text(document, encoding="utf-8")
    (output / "report.html").write_text(_language_index(data_kind), encoding="utf-8")
    root = Path(__file__).resolve().parent.parent
    source_hashes = {f"{folder}/{path.name}": sha256(path.read_bytes())
                     for folder in ("quant_research", "sector_backtest", "hkquant")
                     for path in sorted((root / folder).glob("*.py"))}
    manifest = {
        "schema_version": "quant_research_report_v0.1", "version": __version__,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_kind": data_kind, "input_sha256": input_sha256, "source_label": source_label,
        "config": result["config"], "factor_config": result.get("factor_config"),
        "report_lineage": result.get("report_lineage"),
        "period_status": result["period_status"],
        "versions": {"python": platform.python_version(), **{n: version(n) for n in ("numpy", "pandas", "exchange-calendars", "yfinance")}},
        "source_sha256": source_hashes,
        "artifacts_sha256": {path.name: sha256(path.read_bytes()) for path in sorted(output.iterdir()) if path.is_file()},
        "limitations": limitations,
        "report_languages": list(REPORT_FILES), "report_files": dict(REPORT_FILES),
        "limitations_bilingual": bilingual_limits,
    }
    (output / "manifest.json").write_text(_json(manifest), encoding="utf-8")
    return output / "report.html"
