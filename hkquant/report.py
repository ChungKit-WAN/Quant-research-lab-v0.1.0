"""Small, offline HTML report. All source labels and table cells are escaped."""

from html import escape
from pathlib import Path

import pandas as pd


def write_report(path: Path, latest: pd.DataFrame, coverage: pd.DataFrame, manifest: dict) -> None:
    columns = ["ticker", "rank", "rolling_mean_rank", "rolling_rank", "score",
               "group_score_momentum", "group_score_reversal", "group_score_risk",
               "group_score_liquidity", "reason"]
    names = {"ticker": "股票代码", "rank": "当月排名", "rolling_mean_rank": "近几月平均名次",
             "rolling_rank": "滚动排名", "score": "综合分", "group_score_momentum": "动量分",
             "group_score_reversal": "反转分", "group_score_risk": "低风险分",
             "group_score_liquidity": "量价流动性分", "reason": "数据状态"}
    table = latest[columns].rename(columns=names).to_html(index=False, escape=True, na_rep="—", float_format=lambda n: f"{n:.3f}")
    coverage_table = coverage.to_html(index=False, escape=True)
    period = escape(manifest["latest_month_anchor"][:7])
    n = int(manifest["ticker_count"])
    source = escape(str(manifest["source"].get("source", "unknown")))
    window = int(manifest["config"]["ranking_window"])
    market = "美股" if manifest.get("market") == "US" else "港股"
    heading = "US EQUITY" if manifest.get("market") == "US" else "HONG KONG"
    limits = "".join(f"<li>{escape(str(item))}</li>" for item in manifest["limitations"])
    quality_events = manifest["source"].get("quality_events", [])
    quality = "未发现已返回记录中的全空价格行。尚未独立核对交易日历。"
    if quality_events:
        quality = ("以下原始记录已保留，计算保留缺口，受影响的窗口不会跳过缺失日：" +
                   "、".join(escape(f"{e['ticker']} {e['date']} ({e['issue']})") for e in quality_events))
    content = f"""<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{market}多因子研究 · {period}</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f3f5f8;color:#182632;font:15px/1.7 'Segoe UI','Microsoft YaHei',sans-serif}}
main{{max-width:1320px;margin:auto;padding:40px 24px}}h1{{font-size:30px;margin:5px 0 12px}}h2{{font-size:20px;margin:0 0 14px}}
.eyebrow{{font-size:12px;letter-spacing:2px;color:#366f68}}.sub{{color:#51616d}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:24px 0}}
.card,section{{background:white;border:1px solid #e0e6ed;border-radius:12px;padding:22px}}.number{{font-size:30px;font-weight:650;color:#155d51}}
section{{margin:20px 0}}.notice{{background:#fff5dc;border-left:4px solid #b88310;padding:15px 20px}}.scroll{{overflow-x:auto}}
table{{border-collapse:collapse;width:100%;font-size:13px;border:none}}th{{text-align:left;background:#eef4f2;white-space:nowrap}}td,th{{padding:10px;border-bottom:1px solid #e5e9ed;border-left:none;border-right:none}}td{{white-space:nowrap}}
li{{margin:6px 0}}a{{color:#176a8b}}code{{background:#edf1f5;padding:2px 5px;border-radius:4px}}@media(max-width:720px){{.cards{{grid-template-columns:repeat(2,1fr)}}main{{padding:20px 12px}}}}
</style><main>
<div class="eyebrow">{heading} · MULTI-FACTOR RESEARCH</div>
<h1>{market}数据与因子研究</h1>
<p class="sub">排名月份 {period} · 来源 {source} · 截止日期 {escape(manifest['as_of'])}</p>
<div class="notice"><strong>当前完成数据保存、指标计算和排名阶段。</strong>本页没有模拟交易或收益率。默认股票是固定样本，尚未核验历史指数成分股。</div>
<div class="cards"><div class="card">候选指标<div class="number">100</div></div>
<div class="card">已实现量价指标<div class="number">65</div></div>
<div class="card">待历史财报数据<div class="number">35</div></div>
<div class="card">本次股票数量<div class="number">{n}</div></div></div>
<section><h2>{period} 研究排名</h2><p>当月有效股票 {manifest['latest_eligible']} 只；连续 {window} 个月有效排名 {manifest['latest_rolling_eligible']} 只。
综合分越高越靠前，名次越小越靠前。滚动排名使用最近 {window} 个连续月份的排名百分位均值，避免股票池规模变化直接影响平均值。
每类先平均其指标得分，再应用类别权重。表中平均名次供辅助理解。</p>
<div class="scroll">{table}</div><p class="sub">空白表示历史不足、缺少数据或月份不连续，不会填成零分。股票代码仅用于研究展示。</p></section>
<section><h2>数据覆盖</h2><p>{quality}</p><div class="scroll">{coverage_table}</div></section>
<section><h2>下一阶段</h2><p>核验历史股票池与交易日历 → 接入按公告时间对齐的财报 → 逐笔持仓、现金与费用 → 样本外比较。</p>
<p>先比较当月排名和 {window} 个月平均排名，并保持股票池、资金和交易规则一致。当前类别权重只是待验证的初始设定。</p></section>
<section><h2>复现与限制</h2><p>本目录保存因子登记册、月度结果及 <code>manifest.json</code>。美股流程的原始快照与计算版本保存在两个独立数据库中，批次关联、参数、来源与文件指纹均有记录。</p><ul>{limits}</ul></section>
</main></html>"""
    path.write_text(content, encoding="utf-8")
