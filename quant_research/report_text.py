"""Chinese/English presentation text; machine-readable identifiers stay stable."""

STRATEGIES = {
    "equal_weight": ("等权配置", "Equal weight"),
    "sample_min_variance": ("样本协方差最小方差", "Sample-covariance minimum variance"),
    "shrinkage_min_variance": ("常相关收缩最小方差", "Constant-correlation shrinkage minimum variance"),
    "multifactor_top_n": ("多因子前 N 名等权选股", "Equal-weight multifactor Top N"),
}

PERIODS = {
    "full": ("完整研究期", "Full research period"),
    "development": ("开发期", "Development period"),
    "holdout": ("留出期", "Holdout period"),
}

CONFIG_FIELDS = {
    "tickers": ("固定研究标的", "Fixed research universe"),
    "lookback": ("最低历史长度／ETF 风险估计窗口（收益观察数）", "Minimum history / ETF risk window (return observations)"),
    "research_start": ("研究起始日期", "Research start date"),
    "holdout_start": ("留出期起始日期", "Holdout start date"),
    "cost_bps": ("每笔买入或卖出费用（基点）", "Cost per buy or sell notional (basis points)"),
    "max_weight": ("单资产目标权重上限", "Maximum target weight per asset"),
    "initial_cash": ("初始资本（记账单位）", "Initial capital (accounting units)"),
    "top_n": ("选股数量", "Number of selected stocks"),
    "ranking_window": ("排名平滑窗口（连续月数）", "Rank smoothing window (consecutive months)"),
    "implemented_factor_count": ("已实现因子数量", "Implemented factor count"),
    "group_weights": ("因子组权重", "Factor group weights"),
}

GROUPS = {
    "momentum": ("动量", "Momentum"), "reversal": ("反转", "Reversal"),
    "risk": ("风险", "Risk"), "liquidity": ("流动性", "Liquidity"),
}

# The English strings are also retained in JSON manifests for compatibility.
LIMITATIONS = {
    "Monthly signals at close; execution at the next XNYS session close. New positions earn returns only after execution.":
        "月末收盘后产生信号，在下一 XNYS 交易日收盘执行；新持仓仅获得成交之后的收益。",
    "Fixed selected universe; no historical membership or delisted-asset reconstruction. Selection and survivorship bias remain.":
        "使用预先选定的固定标的，未重建历史成分或退市资产；仍存在选择偏差和幸存者偏差。",
    "Adjusted-price synthetic units, not an independently verified raw-share/dividend ledger. Do not add dividends twice.":
        "账本使用复权价格对应的合成份额，原始股数及现金分红账本尚未独立核验；不得重复计入分红。",
    "XNYS regular sessions are a calendar proxy; fractional units and zero cash interest are assumed.":
        "使用 XNYS 常规交易日作为日历代理；假设允许小数份额，现金利息为零。",
    "Costs apply to every buy/sell notional, including entry. Spread, market impact, volume limits, and partial fills are not modeled.":
        "按每笔买入或卖出金额收取费用，包含首次建仓；尚未模拟买卖价差、市场冲击、成交量限制或部分成交。",
    "Holdout is a date partition, not certification that results were unseen. No claim of statistical significance or predictive power.":
        "留出期只是日期分区，并不证明此前未观察过结果；本报告不声称具有统计显著性或预测能力。",
    "Annualization uses 252 sessions. Targets obey the cap; daily weights may drift above it. No forced terminal liquidation.":
        "年化按 252 个交易日计算。调仓目标遵守权重上限，日常实际权重可能因价格变化超过上限；期末不强制清仓。",
    "SYNTHETIC DATA — pipeline demonstration only. These numbers are not historical investment performance.":
        "合成数据：仅用于演示程序流程，报告中的数值并非历史投资业绩。",
    "User-supplied prices: data rights, adjustments and historical availability have not been independently verified.":
        "用户提供的行情：数据使用权、复权处理及历史可得性尚未经过独立核验。",
    "The fixed supplied universe can contain selection and survivorship bias; historical membership and delisted-stock coverage are not verified.":
        "输入的固定股票池可能存在选择偏差和幸存者偏差；历史成分与退市股票覆盖尚未核实。",
    "Causal signals do not make the vendor data a point-in-time database; adjusted prices can be revised retrospectively.":
        "信号仅使用过去数据，并不意味着数据商提供了历史时点数据库；复权价格可能被事后修订。",
    "Factor directions and group weights are research hypotheses, not validated alpha.":
        "因子方向与分组权重属于研究假设，尚未验证能否产生超额收益。",
    "The common ledger uses synthetic adjusted-price wealth, fractional units, and proportional costs; it is not a raw-share brokerage ledger.":
        "共用账本按复权合成财富、小数份额及比例费用记账，并非券商的原始股票账户账本。",
    "This version uses the XNYS regular-session calendar for a fixed US universe.":
        "本版本面向固定美国市场标的，使用 XNYS 常规交易日历。",
}

SOURCES = {
    "Deterministic synthetic fixture (seed 20261019; OHLCV seed 1019)":
        "确定性合成样本（价格随机种子 20261019；OHLCV 随机种子 1019）",
    "Original local ETF dataset; canonical JSON SHA-256":
        "原本地 ETF 数据集；输入指纹采用规范 JSON 的 SHA-256",
}
