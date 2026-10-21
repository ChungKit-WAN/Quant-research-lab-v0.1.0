"""Predeclared monthly stock research experiments and bilingual evidence.

This is a descriptive sensitivity study, not parameter optimization or proof
that a date-based holdout has never been inspected. Every attempted experiment,
including failures, is retained. The plan is written before any run starts.
"""

from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import html
import json
from numbers import Integral
from pathlib import Path

import numpy as np
import pandas as pd

from hkquant.ranking import DEFAULT_WEIGHTS
from sector_backtest.pipeline import MonthlyConfig
from .stock import _prepare_factor_inputs, _run_factor_monthly_prepared


def _json(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def experiment_plan(config, *, top_n=4, ranking_window=3, group_weights=None):
    """Choose a small deterministic experiment set without looking at returns."""
    if not isinstance(config, MonthlyConfig):
        raise TypeError("config must be a MonthlyConfig")
    if (isinstance(top_n, bool) or not isinstance(top_n, Integral)
            or not 1 <= top_n <= len(config.tickers)):
        raise ValueError("top_n must be a positive integer within the universe")
    if (isinstance(ranking_window, bool) or not isinstance(ranking_window, Integral)
            or ranking_window < 1):
        raise ValueError("ranking_window must be a positive integer")
    weights = dict(DEFAULT_WEIGHTS if group_weights is None else group_weights)
    if set(weights) != set(DEFAULT_WEIGHTS):
        raise ValueError("group_weights must name all four implemented factor groups")
    weights = {key: float(value) for key, value in weights.items()}
    if (not all(np.isfinite(value) and value >= 0 for value in weights.values())
            or not np.isclose(sum(weights.values()), 1.0, rtol=0, atol=1e-10)):
        raise ValueError("group_weights must be finite, nonnegative and sum to one")

    base = {"config": asdict(config), "top_n": int(top_n),
            "ranking_window": int(ranking_window), "group_weights": weights}
    experiments = [{"id": "baseline", "kind": "baseline", **base}]
    for cost in (5.0, 10.0, 20.0):
        if cost != config.cost_bps:
            experiments.append({"id": f"cost_{int(cost)}bps", "kind": "cost",
                                **base, "config": asdict(replace(config, cost_bps=cost))})
    # Never loosen the cap merely to make a holdings experiment run.
    candidates = [top_n + 1, top_n - 1]
    alternate = next((n for n in candidates if 1 <= n <= len(config.tickers)
                      and 1 / n <= config.max_weight + 1e-12), None)
    skipped = []
    if alternate is not None:
        experiments.append({"id": f"holdings_{alternate}", "kind": "holdings",
                            **base, "top_n": int(alternate)})
    else:
        skipped.append({"kind": "holdings", "reason": "no_adjacent_holding_count_satisfies_universe_and_cap"})
    window = 1 if ranking_window != 1 else 3
    experiments.append({"id": f"ranking_window_{window}", "kind": "ranking_window",
                        **base, "ranking_window": window})
    for group in weights:
        remaining = sum(value for key, value in weights.items() if key != group)
        altered = {key: (value / remaining if key != group and remaining > 0 else 0.0)
                   for key, value in weights.items()}
        experiment = {"id": f"without_{group}", "kind": "factor_group",
                      **base, "removed_group": group, "group_weights": altered}
        if remaining <= 0:
            experiment["invalid_reason"] = "Cannot remove the only positively weighted factor group"
        experiments.append(experiment)
    return {"schema_version": "validation_plan_v0.11", "experiments": experiments,
            "skipped_variations": skipped,
            "selection_policy": "predeclared_no_selection_of_best_return",
            "group_removal_policy": "zero_score_weight_keep_all_65_factor_eligibility",
            "benchmark": "same_universe_equal_weight_same_cost_and_execution_schedule",
            "period_policy": "continuous_ledger_split_by_holdout_start_not_certified_unseen"}


def _metric_rows(experiment, result):
    benchmarks = {row["period"]: row for row in result["metrics"]
                  if row["strategy"] == "equal_weight"}
    rows = []
    for metric in result["metrics"]:
        row = {"experiment": experiment["id"], "kind": experiment["kind"],
               "cost_bps": experiment["config"]["cost_bps"],
               "top_n": experiment["top_n"], "ranking_window": experiment["ranking_window"],
               **{key: value for key, value in metric.items()
                  if not isinstance(value, (dict, list, tuple))}}
        benchmark = benchmarks.get(metric["period"])
        matched = benchmark is not None and all(
            metric[key] == benchmark[key]
            for key in ("first_session", "last_session", "observations"))
        row["benchmark_comparable"] = bool(matched)
        row["benchmark_net_cagr"] = benchmark["net_cagr"] if matched else None
        row["net_cagr_difference_vs_equal_weight"] = (
            metric["net_cagr"] - benchmark["net_cagr"] if matched else None)
        row["net_total_return_difference_vs_equal_weight"] = (
            metric["net_total_return"] - benchmark["net_total_return"] if matched else None)
        rows.append(row)
    return rows


def _sensitivity(rows):
    summaries = []
    for period in ("full", "development", "holdout"):
        eligible = [row for row in rows if row["strategy"] == "multifactor_top_n"
                    and row["period"] == period and row["benchmark_comparable"]]
        baseline = next((row for row in eligible if row["experiment"] == "baseline"), None)
        matched = [row for row in eligible if baseline is not None and all(
            row[key] == baseline[key] for key in ("first_session", "last_session", "observations"))]
        differences = [row["net_cagr_difference_vs_equal_weight"] for row in matched]
        summaries.append({
            "period": period, "comparable_experiments": len(matched),
            "excluded_experiments": len(eligible) - len(matched),
            "minimum_net_cagr_difference": min(differences) if differences else None,
            "maximum_net_cagr_difference": max(differences) if differences else None,
            "difference_sign_changes": (min(differences) < 0 < max(differences)) if differences else None,
            "interpretation": "descriptive_range_not_statistical_significance_or_forecast",
        })
    return summaries


_ZH = {
    "experiment": "实验", "kind": "实验类别", "cost_bps": "单边成本（bp）", "top_n": "持股数",
    "ranking_window": "排名平滑月数", "strategy": "策略", "period": "区间",
    "first_session": "首个交易日", "last_session": "末个交易日", "observations": "交易日数",
    "opening_nav": "期初净值", "closing_nav": "期末净值", "net_total_return": "扣费后总收益",
    "net_cagr": "扣费后 CAGR", "annualized_volatility": "年化波动率", "maximum_drawdown": "最大回撤",
    "daily_loss_cvar_95": "日损失 CVaR 95", "tail_observation_mass": "尾部观测概率质量",
    "buy_notional": "买入名义额", "sell_notional": "卖出名义额", "traded_notional": "买卖名义额合计",
    "transaction_costs": "交易费用", "traded_notional_over_opening_nav": "买卖额／期初净值",
    "transaction_costs_over_opening_nav": "费用／期初净值", "rebalance_count": "调仓次数",
    "benchmark_comparable": "同区间基准可比", "benchmark_net_cagr": "等权基准 CAGR",
    "net_cagr_difference_vs_equal_weight": "CAGR 与等权差额",
    "net_total_return_difference_vs_equal_weight": "总收益与等权差额",
    "ledger_consistency_verified": "账本一致性检查", "schema_version": "数据结构版本",
    "input_sha256": "账本输入 SHA256", "implementation_sha256": "实现 SHA256",
}
_PERCENTAGES = {"net_total_return", "net_cagr", "annualized_volatility", "maximum_drawdown",
                "daily_loss_cvar_95", "benchmark_net_cagr", "net_cagr_difference_vs_equal_weight",
                "net_total_return_difference_vs_equal_weight"}


def _render(summary, language):
    zh = language == "zh-CN"

    def text(cn, en):
        return html.escape(cn if zh else en)

    def cell(key, value):
        if value is None:
            return "—"
        if key in _PERCENTAGES:
            return f"{value:.3%}"
        if isinstance(value, float):
            return f"{value:.8g}"
        if key in ("period", "strategy") and zh:
            value = {"full": "全期", "development": "开发期", "holdout": "按日期划分的留出期",
                     "equal_weight": "同股票池等权", "multifactor_top_n": "多因子选股"}.get(value, value)
        return html.escape(str(value))

    experiment_rows = []
    for row in summary["experiments"]:
        experiment = row["parameters"]
        error = row.get("error", {}).get("message", "")
        values = [row["id"], row["status"], str(experiment["config"]["cost_bps"]),
                  str(experiment["top_n"]), str(experiment["ranking_window"]),
                  json.dumps(experiment["group_weights"], ensure_ascii=False), error]
        experiment_rows.append("<tr>" + "".join(f"<td>{html.escape(value)}</td>" for value in values) + "</tr>")
    columns = list(dict.fromkeys(key for row in summary["metrics"] for key in row))
    metric_rows = ["<tr>" + "".join(f"<td>{cell(key, row.get(key))}</td>" for key in columns) + "</tr>"
                   for row in summary["metrics"]]
    sensitivity = []
    for row in summary["sensitivity"]:
        lo, hi = row["minimum_net_cagr_difference"], row["maximum_net_cagr_difference"]
        interval = "—" if lo is None else f"{lo:.3%} → {hi:.3%}"
        count = row["comparable_experiments"]
        signal = (text("正负号发生变化", "both positive and negative differences observed")
                  if row["difference_sign_changes"] else
                  text("没有观察到严格的正负号切换", "no strict positive-to-negative sign change observed"))
        sensitivity.append(f'<li>{cell("period", row["period"])}: {count} '
                           + text("组可比实验；CAGR 与等权差额范围", "comparable experiments; CAGR difference range")
                           + f" {interval}; {signal}.</li>")
    disclaimer = text(
        "按日期划分开发期和留出期；这不证明留出期从未用于调参。全部实验都已公开，不能再把本次查看的历史区间称为未见测试集。"
        "若要建立真正前瞻验证，应先冻结本次计划与代码，再另行收集冻结后的未来数据。",
        "Development and holdout are chronological partitions, not certification of unseen data. All experiments are disclosed; "
        "history inspected in this report must not subsequently be described as an unseen test set. "
        "Prospective validation requires freezing this plan and code before separately collecting future observations.")
    demo = (text("合成数据：仅验证程序流程，不代表真实历史投资业绩。", "SYNTHETIC DATA: pipeline checks only, not historical investment performance.")
            if summary["data_kind"] == "synthetic_demo" else
            text("真实数据研究：数据源、复权与历史股票池尚未独立认证。", "Market-data research: source, adjustments and historical universe are not independently certified."))
    other = "validation_en.html" if zh else "validation_zh.html"
    title = text("v0.11 研究验证报告", "v0.11 Research Validation Report")
    headers = ("实验", "状态", "成本（bp）", "持股数", "平滑月数", "类别权重", "失败原因") if zh else (
        "Experiment", "Status", "Cost (bp)", "Holdings", "Ranking months", "Group weights", "Failure reason")
    return f'''<!doctype html><html lang="{language}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>
body{{margin:0;background:#0b1220;color:#e2e8f0;font:15px/1.65 system-ui,sans-serif}}main{{max-width:1320px;margin:auto;padding:30px 24px}}
a{{color:#7dd3fc}}h1{{font-size:30px}}h2{{margin-top:32px}}.notice{{border:1px solid #eab308;padding:16px;border-radius:10px;color:#fde68a}}
.table{{overflow:auto;max-height:680px}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{padding:10px;text-align:left;border-bottom:1px solid #334155;white-space:nowrap}}
th{{position:sticky;top:0;background:#182337}}.muted{{color:#94a3b8}}code{{overflow-wrap:anywhere}}li{{margin:10px 0}}</style></head><body><main>
<nav><a href="{other}">{text("English report", "中文报告")}</a> · <a href="validation.json">JSON</a> · <a href="validation_metrics.csv">CSV</a> · <a href="validation_plan.json">{text("运行前固定计划", "Predeclared plan")}</a></nav>
<h1>{title}</h1><p class="notice">{demo}<br>{disclaimer}</p>
<p>{text("来源", "Source")}: {html.escape(summary["source_label"])}<br>
{text("研究起点 / 留出起点", "Research start / holdout start")}: {html.escape(summary["config"]["research_start"])} / {html.escape(summary["config"]["holdout_start"])}</p>
<h2>{text("全部实验与失败记录", "All experiments, including failures")}</h2><div class="table"><table><thead><tr>{''.join('<th>'+html.escape(h)+'</th>' for h in headers)}</tr></thead><tbody>{''.join(experiment_rows)}</tbody></table></div>
<h2>{text("描述性敏感度", "Descriptive sensitivity")}</h2><ul>{''.join(sensitivity)}</ul>
<p>{text("上述范围包括所有成功且与基准区间一致的实验。正负号变化表示观察到的相对表现对参数敏感；没有变化不证明稳健、显著或可预测。失败实验与不可比较区间不能当作零收益。", "Ranges include every successful experiment with an aligned benchmark interval. A sign change shows observed relative performance is parameter-sensitive; no change does not prove robustness, significance or predictability. Failed experiments and incomparable periods are not zero returns.")}</p>
<h2>{text("全部分期绩效指标", "All performance metrics by period")}</h2><p class="muted">{text("横向滚动查看全部字段；CSV 保留原始数值。各实验均使用同股票池、同成本及同执行时点的等权基准。", "Scroll horizontally for every field; CSV preserves raw values. Each experiment uses an equal-weight benchmark with the same universe, cost and execution timing.")}</p>
<div class="table"><table><thead><tr>{''.join('<th>'+html.escape(_ZH.get(key,key) if zh else key)+'</th>' for key in columns)}</tr></thead><tbody>{''.join(metric_rows)}</tbody></table></div>
<h2>{text("计算口径", "Conventions")}</h2><ul>
<li>{text("月末信号、下一交易日收盘执行，持仓之后才获得收益；开发期与留出期共享连续账本，分期不重置资金。", "Month-end signals execute at the next session close; new positions earn returns afterward. Development and holdout share one continuous ledger without resetting capital.")}</li>
<li>{text("CAGR 按 252 个交易日年化；与基准的 CAGR 差额是描述性差额，不是经风险调整的 alpha。费用按每笔买卖名义额收取，包括首次建仓。", "CAGR uses 252 trading sessions; its benchmark difference is descriptive, not risk-adjusted alpha. Proportional costs apply to each buy and sell, including entry.")}</li>
<li>{text("因子组剔除将该组评分权重归零并归一化其余权重；仍要求全部 65 项量价因子完整，保持资格规则一致。35 项财务因子未参与。", "Group ablations set one score weight to zero and normalize the others. All 65 price/volume factors remain required for eligibility, preserving a common eligibility rule. The 35 financial factors are not used.")}</li>
<li>{text("固定股票池可能存在选择及幸存者偏差；复权历史值可能被数据商修订。运行成功不是独立数据核验。", "A fixed universe can contain selection and survivorship bias; vendors may revise adjusted history. Successful execution is not independent data verification.")}</li></ul>
<p class="muted">{text("计划 SHA256", "Plan SHA256")}: <code>{summary["plan_sha256"]}</code><br>{text("输入 SHA256", "Input SHA256")}: <code>{summary["input_sha256"]}</code></p>
</main></body></html>'''


def run_validation(long_prices, config, output, *, top_n=4, ranking_window=3,
                   group_weights=None, data_kind="user_supplied_adjusted_prices",
                   source_label="", input_sha256=None):
    """Run and retain every planned experiment; return a JSON-safe summary.

    ``output`` must be new or empty. Failure of one experiment is recorded and
    does not suppress subsequent experiments. Input prices are never changed.
    ``input_sha256`` may identify the caller's exact serialized input bytes;
    the independently calculated frame fingerprint is also always retained.
    """
    plan = experiment_plan(config, top_n=top_n, ranking_window=ranking_window,
                           group_weights=group_weights)
    output = Path(output)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Validation output must be a new or empty directory")
    frame_bytes = long_prices.to_csv(index=False, date_format="%Y-%m-%d", lineterminator="\n").encode("utf-8")
    frame_sha256 = _digest(frame_bytes)
    if input_sha256 is not None and (not isinstance(input_sha256, str)
                                    or len(input_sha256) != 64
                                    or any(c not in "0123456789abcdef" for c in input_sha256)):
        raise ValueError("input_sha256 must be a lowercase SHA-256 hex digest")
    output.mkdir(parents=True, exist_ok=True)
    experiment_dir = output / "experiments"
    experiment_dir.mkdir()
    plan.update({"created_at_utc": datetime.now(timezone.utc).isoformat(),
                 "data_kind": data_kind, "input_frame_sha256": frame_sha256,
                 "source_label": str(source_label)})
    plan_bytes = (_json(plan) + "\n").encode("utf-8")
    (output / "validation_plan.json").write_bytes(plan_bytes)
    summary = {"schema_version": "research_validation_v0.11", "config": asdict(config),
               "data_kind": data_kind, "source_label": str(source_label),
               "input_sha256": input_sha256 or frame_sha256, "input_frame_sha256": frame_sha256,
               "plan_sha256": _digest(plan_bytes), "plan": plan,
               "unseen_holdout_certified": False, "experiments": [], "metrics": []}
    prepared, preparation_error = None, None
    try:
        prepared = _prepare_factor_inputs(long_prices, config)
    except Exception as exc:
        preparation_error = exc
    for experiment in plan["experiments"]:
        record = {"id": experiment["id"], "parameters": experiment,
                  "artifact": f"experiments/{experiment['id']}.json"}
        try:
            if "invalid_reason" in experiment:
                raise ValueError(experiment["invalid_reason"])
            if preparation_error is not None:
                raise preparation_error
            result = _run_factor_monthly_prepared(
                prepared, MonthlyConfig(**experiment["config"]),
                top_n=experiment["top_n"], ranking_window=experiment["ranking_window"],
                group_weights=experiment["group_weights"])
            metrics = _metric_rows(experiment, result)
            # Serialize before marking success: invalid numbers must not silently
            # enter a successful artifact or the combined summary.
            artifact = _json({"status": "completed", "parameters": experiment, "result": result})
            record.update(status="completed", period_status=result["period_status"])
            summary["metrics"].extend(metrics)
        except Exception as exc:
            record.update(status="failed", error={"type": type(exc).__name__, "message": str(exc)})
            artifact = _json(record)
        (output / record["artifact"]).write_text(artifact + "\n", encoding="utf-8")
        summary["experiments"].append(record)
    summary["sensitivity"] = _sensitivity(summary["metrics"])
    summary["completed_experiments"] = sum(row["status"] == "completed" for row in summary["experiments"])
    summary["failed_experiments"] = len(summary["experiments"]) - summary["completed_experiments"]
    summary["status"] = ("completed" if summary["failed_experiments"] == 0 else
                         "partial_failure" if summary["completed_experiments"] else "failed")
    summary["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    columns = None if summary["metrics"] else ["experiment", "strategy", "period"]
    pd.DataFrame(summary["metrics"], columns=columns).to_csv(
        output / "validation_metrics.csv", index=False, encoding="utf-8-sig")
    for language, filename in (("en", "validation_en.html"), ("zh-CN", "validation_zh.html")):
        (output / filename).write_text(_render(summary, language), encoding="utf-8")
    summary["artifacts_sha256"] = {
        path.relative_to(output).as_posix(): _digest(path.read_bytes())
        for path in sorted(output.rglob("*")) if path.is_file()}
    (output / "validation.json").write_text(_json(summary) + "\n", encoding="utf-8")
    return summary
