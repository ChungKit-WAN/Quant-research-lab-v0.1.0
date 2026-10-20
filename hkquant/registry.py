"""The research universe of 100 candidate indicators, not 100 validated signals."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FactorSpec:
    id: str
    group: str
    label: str
    formula: str
    direction: int
    min_observations: int
    status: str


def _build_registry() -> tuple[FactorSpec, ...]:
    specs: list[FactorSpec] = []

    def add(group, identifier, label, formula, direction, observations):
        specs.append(FactorSpec(identifier, group, label, formula, direction,
                                observations, "implemented"))

    for n in (21, 42, 63, 126, 189, 252):
        add("momentum", f"mom_return_{n}", f"{n}日动量", f"P[t]/P[t-{n}]-1", 1, n + 1)
    for n in (63, 126, 189, 252):
        add("momentum", f"mom_skip21_{n}", f"{n}日动量（跳过最近21日）",
            f"P[t-21]/P[t-{n}]-1", 1, n + 1)
    for n in (21, 63, 126, 252):
        add("momentum", f"mom_ma_distance_{n}", f"价格偏离{n}日均线",
            f"P[t]/mean(P,{n})-1", 1, n)
    for fast, slow in ((21, 63), (21, 126), (63, 126), (63, 252)):
        add("momentum", f"mom_ma_ratio_{fast}_{slow}", f"{fast}/{slow}日均线趋势",
            f"mean(P,{fast})/mean(P,{slow})-1", 1, slow)
    for n in (63, 126):
        add("momentum", f"mom_positive_days_{n}", f"{n}日上涨比例",
            f"mean(1[r>0],{n})", 1, n + 1)

    for n in (1, 3, 5, 10):
        add("reversal", f"rev_return_{n}", f"{n}日短期涨幅（反转假设）",
            f"P[t]/P[t-{n}]-1", -1, n + 1)
    for n in (21, 63):
        add("reversal", f"rev_price_zscore_{n}", f"{n}日价格标准分",
            f"(P[t]-mean(P,{n}))/std(P,{n},ddof=1)", -1, n)
    for n in (14, 28):
        add("reversal", f"rev_rsi_{n}", f"{n}日简单均值RSI",
            f"100*mean(max(diff(P),0),{n})/mean(abs(diff(P)),{n})", -1, n + 1)
    for n in (5, 10):
        add("reversal", f"rev_negative_days_{n}", f"{n}日下跌比例（反转假设）",
            f"mean(1[r<0],{n})", 1, n + 1)

    for n in (20, 60, 120, 252):
        add("risk", f"risk_volatility_{n}", f"{n}日年化波动率",
            f"std(r,{n},ddof=1)*sqrt(252)", -1, n + 1)
    for n in (20, 60, 120):
        add("risk", f"risk_downside_{n}", f"{n}日下行偏差",
            f"sqrt(mean(min(r,0)^2,{n})*252)", -1, n + 1)
    for n in (63, 126, 252):
        add("risk", f"risk_max_drawdown_{n}", f"{n}日窗口内最大回撤幅度",
            f"max(1-P[u]/cummax(P)[u]) within last {n} prices", -1, n)
    add("risk", "risk_ulcer_63", "63日回撤均方根", "sqrt(mean((1-P/cummax(P))^2)) within last 63 prices", -1, 63)
    for n in (60, 126):
        add("risk", f"risk_tail_loss_{n}", f"{n}日5%收益分位的相反数",
            f"-quantile(r,{n},0.05)", -1, n + 1)
    add("risk", "risk_negative_days_63", "63日下跌比例", "mean(1[r<0],63)", -1, 64)
    add("risk", "risk_vol_of_vol_60", "60日波动率的波动", "std(std(r,20,ddof=1)*sqrt(252),60,ddof=1)", -1, 80)

    for n in (20, 60, 120):
        add("liquidity", f"liq_amount_{n}", f"{n}日平均成交额代理",
            f"mean(close*volume,{n})", 1, n)
    for n in (20, 60, 120):
        add("liquidity", f"liq_volume_{n}", f"{n}日平均成交股数",
            f"mean(volume,{n})", 1, n)
    for n in (20, 60, 120):
        add("liquidity", f"liq_amihud_{n}", f"{n}日非流动性代理",
            f"mean(abs(r)/(close*volume/1e6),{n}); zero amount -> missing", -1, n + 1)
    for n in (20, 60):
        add("liquidity", f"liq_volume_cv_{n}", f"{n}日成交量变异系数",
            f"std(volume,{n},ddof=1)/mean(volume,{n})", -1, n)
    for fast, slow in ((5, 20), (20, 60)):
        add("liquidity", f"liq_volume_ratio_{fast}_{slow}", f"{fast}/{slow}日成交量比",
            f"mean(volume,{fast})/mean(volume,{slow})", 1, slow)
    for fast, slow in ((5, 20), (20, 60)):
        add("liquidity", f"liq_amount_ratio_{fast}_{slow}", f"{fast}/{slow}日成交额代理比",
            f"mean(close*volume,{fast})/mean(close*volume,{slow})", 1, slow)
    for n in (20, 60):
        add("liquidity", f"liq_zero_volume_{n}", f"{n}日零成交记录比例",
            f"mean(1[volume=0],{n})", -1, n)
    for n in (20, 60):
        add("liquidity", f"liq_return_volume_corr_{n}", f"{n}日收益与成交量相关系数",
            f"corr(r,volume,{n})", 1, n + 1)
    add("liquidity", "liq_price_impact_60", "60日波动/成交额代理",
        "std(r,60,ddof=1)/(mean(close*volume,60)/1e6)", -1, 61)

    financial = {
        "value": [
            ("earnings_yield", "盈利收益率", "NI_TTM / market_cap", 1),
            ("book_to_price", "账面市值比", "common_equity / market_cap", 1),
            ("sales_yield", "营收市值比", "revenue_TTM / market_cap", 1),
            ("operating_cashflow_yield", "经营现金流收益率", "CFO_TTM / market_cap", 1),
            ("free_cashflow_yield", "自由现金流收益率", "(CFO_TTM-capex_TTM) / market_cap", 1),
            ("dividend_yield", "现金股息收益率", "cash_dividends_TTM / market_cap", 1),
            ("ebit_ev", "EBIT企业价值比", "EBIT_TTM / EV", 1),
            ("ebitda_ev", "EBITDA企业价值比", "EBITDA_TTM / EV", 1),
            ("revenue_ev", "营收企业价值比", "revenue_TTM / EV", 1),
            ("net_cash_to_cap", "净现金市值比", "(cash-total_debt) / market_cap", 1),
            ("net_current_assets_to_cap", "净流动资产市值比", "(current_assets-total_liabilities) / market_cap", 1),
            ("tangible_book_to_price", "有形净资产市值比", "(common_equity-goodwill-other_intangibles) / market_cap", 1),
            ("retained_earnings_to_cap", "留存收益市值比", "retained_earnings / market_cap", 1),
            ("gross_profit_ev", "毛利企业价值比", "gross_profit_TTM / EV", 1),
            ("shareholder_yield", "股东回报收益率", "(cash_dividends_TTM+buybacks_TTM-share_issuance_TTM) / market_cap", 1),
        ],
        "quality": [
            ("roe", "净资产收益率", "NI_common_TTM / average_common_equity", 1),
            ("roa", "总资产收益率", "NI_TTM / average_total_assets", 1),
            ("gross_margin", "毛利率", "gross_profit_TTM / revenue_TTM", 1),
            ("operating_margin", "营业利润率", "operating_profit_TTM / revenue_TTM", 1),
            ("cash_conversion", "利润现金含量", "CFO_TTM / NI_TTM; NI_TTM>0 required", 1),
            ("accruals", "应计利润比例", "(NI_TTM-CFO_TTM) / average_total_assets", -1),
            ("debt_assets", "有息负债资产比", "total_debt / total_assets", -1),
            ("interest_coverage", "利息保障倍数", "EBIT_TTM / interest_expense_TTM", 1),
            ("current_ratio", "流动比率", "current_assets / current_liabilities", 1),
            ("cash_assets", "现金资产比", "cash / total_assets", 1),
        ],
        "growth": [
            ("revenue_yoy", "营收同比增长", "revenue_TTM/revenue_TTM_1y_ago-1", 1),
            ("income_yoy", "净利润同比变化", "(NI_TTM-NI_TTM_1y_ago)/abs(NI_TTM_1y_ago)", 1),
            ("eps_yoy", "每股盈利同比变化", "(EPS_TTM-EPS_TTM_1y_ago)/abs(EPS_TTM_1y_ago)", 1),
            ("gross_profit_yoy", "毛利同比变化", "(gross_profit_TTM-gross_profit_TTM_1y_ago)/abs(gross_profit_TTM_1y_ago)", 1),
            ("cashflow_yoy", "经营现金流同比变化", "(CFO_TTM-CFO_TTM_1y_ago)/abs(CFO_TTM_1y_ago)", 1),
            ("book_equity_yoy", "净资产同比增长", "common_equity/common_equity_1y_ago-1", 1),
            ("assets_yoy", "资产同比增长（谨慎扩张假设）", "total_assets/total_assets_1y_ago-1", -1),
            ("operating_profit_yoy", "营业利润同比变化", "(operating_profit_TTM-operating_profit_TTM_1y_ago)/abs(operating_profit_TTM_1y_ago)", 1),
            ("dividends_yoy", "股息同比增长", "cash_dividends_TTM/cash_dividends_TTM_1y_ago-1", 1),
            ("profit_margin_change", "净利率同比变化", "NI_TTM/revenue_TTM-NI_TTM_1y_ago/revenue_TTM_1y_ago", 1),
        ],
    }
    for group, rows in financial.items():
        for identifier, label, formula, direction in rows:
            specs.append(FactorSpec(f"{group}_{identifier}", group, label, formula,
                                    direction, 0, "awaiting_pit_fundamentals"))
    return tuple(specs)


FACTOR_SPECS = _build_registry()
IMPLEMENTED_SPECS = tuple(s for s in FACTOR_SPECS if s.status == "implemented")
