# 100 项候选指标登记册

这里的 100 指候选指标数量，不表示 100 个独立投资逻辑，更不表示已验证有效。当前实际计算 **65 项价格、成交量指标**；**35 项财务指标等待历史时点数据接入**，状态为 `awaiting_pit_fundamentals`。程序不会用当前财报填历史，也不会把缺失财务值补成 0。

代码中的唯一登记来源是 `hkquant/registry.py` 的 `FACTOR_SPECS`。日期窗口、方向和状态均可在该文件核对。方向 +1 表示暂设原始指标越大评分越高，−1 表示越小评分越高；方向仅为待检验假设，不是收益保证。尤其流动性和成长中的部分方向可能依赖市场环境。

## 计算口径

- `P` = `adj_close`，`r = P[t]/P[t-1]-1`，`V` = 原始成交股数，`A = close * volume`。A 只是以收盘价估算的成交额代理，不是真实成交金额，也不是自由流通股换手率。
- 全部收益、趋势、波动及回撤指标使用复权价格。65 项目前不使用 open/high/low，接口保留它们供交易层与后续研究使用。
- 窗口包含当日且只看过去，以输入表中按日期排列的观察记录计数。数据层必须提供日线；本层不凭空补交易日。缺少整行交易日需要数据质量检查发现，不能仅凭滚动窗口视为交易日连续。
- 不前填价格或成交量。窗口内缺失会使需要完整窗口的指标保持 NaN。价量比率分母为零时保持 NaN，不输出无穷大。
- 当日 volume <= 0，或 close/adj_close 无效时，整行指标均为 NaN，不据此生成当日可交易评分。历史的零成交记录仍用于零成交比例；若有合法停牌报价，历史价格序列可能含静止价格，风险估计需结合停牌过滤。缺少报价整行不能当作零成交。
- 最低观察数包含必要的前一期价格。例如 21 日涨幅至少需要 22 条有效价格记录；252 日最大回撤窗口需要 252 条价格记录。
- 标准差均使用样本标准差（ddof=1）。252 为本项目统一采用的年化常数，不代表每个自然年实际有 252 个香港交易日。
- RSI 使用简单滚动平均，非 Wilder 平滑。完整窗口全平时记 50；历史不足仍为 NaN。
- 最大回撤和回撤均方根均在各自窗口内重新建立历史峰值，回撤以正幅度表示。尾部损失是收益 5% 分位的相反数，并非 Expected Shortfall。
- 零成交导致非流动性代理的分母为零时，该日比率缺失，完整滚动窗口也可能暂时缺失；不能把除零当成零冲击。
- Yahoo 的复权历史会随公司行动和数据修订回溯变化，不能视为审计级 point-in-time 数据。程序通过未来追加不变测试，只说明给定输入下算法不引用未来，不证明下载源保存了历史时点版本。原始成交股数也需要关注拆并股的单位变化。
- 不同周期的指标往往高度相关。新增指标应进行分组、相关性与样本外对照检验；增加指标数量本身不意味着增加有效信息。

## 财务接入要求

这 35 项目前不参与任何评分、组合权重或回测。完成以下数据条件并实现、验证代码后，才可改变状态：

1. 保存历史财报的实际公告时间、报告期和当时公布的数值；在策略计算时刻只能关联已经公开的版本，不能按报告期末提前使用，也不能让后来的重述覆盖旧快照。
2. TTM 为最近十二个月，需按可取得的半年/年度报告正确拼接，避免把累计值当单季值重复相加。同比比较必须使用同口径的上一年对应值。
3. 市值用当时价格与当时股数计算，统一财报、市值和现金流的币种及单位，处理多股类别、汇率与公司行动。不得从当前静态接口取市值后复制到历史。
4. 分母为零或不具备经济意义时保留缺失；例如常规估值比率中的市值、EV、净资产分母需按因子设计检验正值。财务公式需按金融/非金融行业适用性筛选，当前没有行业中性化承诺。
5. NI 为归母净利润，CFO 为经营活动净现金流，capex 为正数表示的资本开支流出，EPS 需统一股份调整口径。average 表示对应期初期末平均值；EV 为市值加有息债务、优先股及少数股东权益，减现金及现金等价物。字段映射必须记录来源，缺项不可臆造。

财务项最低日线观察数在登记对象中为 0（不适用），下表显示“—”。这不代表财务指标无需历史数据。

## 动量（20 项）

状态：`implemented`。

| 序号 | 指标 ID | 含义 | 公式 | 方向 | 最低观察数 |
|---:|---|---|---|---:|---:|
| 1 | `mom_return_21` | 21日动量 | `P[t]/P[t-21]-1` | +1 | 22 |
| 2 | `mom_return_42` | 42日动量 | `P[t]/P[t-42]-1` | +1 | 43 |
| 3 | `mom_return_63` | 63日动量 | `P[t]/P[t-63]-1` | +1 | 64 |
| 4 | `mom_return_126` | 126日动量 | `P[t]/P[t-126]-1` | +1 | 127 |
| 5 | `mom_return_189` | 189日动量 | `P[t]/P[t-189]-1` | +1 | 190 |
| 6 | `mom_return_252` | 252日动量 | `P[t]/P[t-252]-1` | +1 | 253 |
| 7 | `mom_skip21_63` | 63日动量跳过最近21日 | `P[t-21]/P[t-63]-1` | +1 | 64 |
| 8 | `mom_skip21_126` | 126日动量跳过最近21日 | `P[t-21]/P[t-126]-1` | +1 | 127 |
| 9 | `mom_skip21_189` | 189日动量跳过最近21日 | `P[t-21]/P[t-189]-1` | +1 | 190 |
| 10 | `mom_skip21_252` | 252日动量跳过最近21日 | `P[t-21]/P[t-252]-1` | +1 | 253 |
| 11 | `mom_ma_distance_21` | 21日均线偏离 | `P/mean(P,21)-1` | +1 | 21 |
| 12 | `mom_ma_distance_63` | 63日均线偏离 | `P/mean(P,63)-1` | +1 | 63 |
| 13 | `mom_ma_distance_126` | 126日均线偏离 | `P/mean(P,126)-1` | +1 | 126 |
| 14 | `mom_ma_distance_252` | 252日均线偏离 | `P/mean(P,252)-1` | +1 | 252 |
| 15 | `mom_ma_ratio_21_63` | 21/63日均线趋势 | `mean(P,21)/mean(P,63)-1` | +1 | 63 |
| 16 | `mom_ma_ratio_21_126` | 21/126日均线趋势 | `mean(P,21)/mean(P,126)-1` | +1 | 126 |
| 17 | `mom_ma_ratio_63_126` | 63/126日均线趋势 | `mean(P,63)/mean(P,126)-1` | +1 | 126 |
| 18 | `mom_ma_ratio_63_252` | 63/252日均线趋势 | `mean(P,63)/mean(P,252)-1` | +1 | 252 |
| 19 | `mom_positive_days_63` | 63日上涨比例 | `mean(1[r>0],63)` | +1 | 64 |
| 20 | `mom_positive_days_126` | 126日上涨比例 | `mean(1[r>0],126)` | +1 | 127 |

## 反转（10 项）

状态：`implemented`。

| 序号 | 指标 ID | 含义 | 公式 | 方向 | 最低观察数 |
|---:|---|---|---|---:|---:|
| 21 | `rev_return_1` | 1日短期涨幅 | `P[t]/P[t-1]-1` | −1 | 2 |
| 22 | `rev_return_3` | 3日短期涨幅 | `P[t]/P[t-3]-1` | −1 | 4 |
| 23 | `rev_return_5` | 5日短期涨幅 | `P[t]/P[t-5]-1` | −1 | 6 |
| 24 | `rev_return_10` | 10日短期涨幅 | `P[t]/P[t-10]-1` | −1 | 11 |
| 25 | `rev_price_zscore_21` | 21日价格标准分 | `(P-mean(P,21))/std(P,21)` | −1 | 21 |
| 26 | `rev_price_zscore_63` | 63日价格标准分 | `(P-mean(P,63))/std(P,63)` | −1 | 63 |
| 27 | `rev_rsi_14` | 14日简单均值RSI | `100*mean(max(diff(P),0),14)/mean(abs(diff(P)),14)` | −1 | 15 |
| 28 | `rev_rsi_28` | 28日简单均值RSI | `100*mean(max(diff(P),0),28)/mean(abs(diff(P)),28)` | −1 | 29 |
| 29 | `rev_negative_days_5` | 5日下跌比例 | `mean(1[r<0],5)` | +1 | 6 |
| 30 | `rev_negative_days_10` | 10日下跌比例 | `mean(1[r<0],10)` | +1 | 11 |

## 波动与风险（15 项）

状态：`implemented`。

| 序号 | 指标 ID | 含义 | 公式 | 方向 | 最低观察数 |
|---:|---|---|---|---:|---:|
| 31 | `risk_volatility_20` | 20日年化波动率 | `std(r,20)*sqrt(252)` | −1 | 21 |
| 32 | `risk_volatility_60` | 60日年化波动率 | `std(r,60)*sqrt(252)` | −1 | 61 |
| 33 | `risk_volatility_120` | 120日年化波动率 | `std(r,120)*sqrt(252)` | −1 | 121 |
| 34 | `risk_volatility_252` | 252日年化波动率 | `std(r,252)*sqrt(252)` | −1 | 253 |
| 35 | `risk_downside_20` | 20日下行偏差 | `sqrt(mean(min(r,0)^2,20)*252)` | −1 | 21 |
| 36 | `risk_downside_60` | 60日下行偏差 | `sqrt(mean(min(r,0)^2,60)*252)` | −1 | 61 |
| 37 | `risk_downside_120` | 120日下行偏差 | `sqrt(mean(min(r,0)^2,120)*252)` | −1 | 121 |
| 38 | `risk_max_drawdown_63` | 63日最大回撤幅度 | `63日窗口内 max(1-P/cummax(P))` | −1 | 63 |
| 39 | `risk_max_drawdown_126` | 126日最大回撤幅度 | `126日窗口内 max(1-P/cummax(P))` | −1 | 126 |
| 40 | `risk_max_drawdown_252` | 252日最大回撤幅度 | `252日窗口内 max(1-P/cummax(P))` | −1 | 252 |
| 41 | `risk_ulcer_63` | 63日回撤均方根 | `63日窗口内 sqrt(mean((1-P/cummax(P))^2))` | −1 | 63 |
| 42 | `risk_tail_loss_60` | 60日尾部损失分位 | `-quantile(r,60,0.05)` | −1 | 61 |
| 43 | `risk_tail_loss_126` | 126日尾部损失分位 | `-quantile(r,126,0.05)` | −1 | 127 |
| 44 | `risk_negative_days_63` | 63日下跌比例 | `mean(1[r<0],63)` | −1 | 64 |
| 45 | `risk_vol_of_vol_60` | 60日波动率的波动 | `std(std(r,20)*sqrt(252),60)` | −1 | 80 |

## 量价与流动性（20 项）

状态：`implemented`。

| 序号 | 指标 ID | 含义 | 公式 | 方向 | 最低观察数 |
|---:|---|---|---|---:|---:|
| 46 | `liq_amount_20` | 20日平均成交额代理 | `mean(A,20)` | +1 | 20 |
| 47 | `liq_amount_60` | 60日平均成交额代理 | `mean(A,60)` | +1 | 60 |
| 48 | `liq_amount_120` | 120日平均成交额代理 | `mean(A,120)` | +1 | 120 |
| 49 | `liq_volume_20` | 20日平均成交股数 | `mean(V,20)` | +1 | 20 |
| 50 | `liq_volume_60` | 60日平均成交股数 | `mean(V,60)` | +1 | 60 |
| 51 | `liq_volume_120` | 120日平均成交股数 | `mean(V,120)` | +1 | 120 |
| 52 | `liq_amihud_20` | 20日非流动性代理 | `mean(abs(r)/(A/1e6),20)` | −1 | 21 |
| 53 | `liq_amihud_60` | 60日非流动性代理 | `mean(abs(r)/(A/1e6),60)` | −1 | 61 |
| 54 | `liq_amihud_120` | 120日非流动性代理 | `mean(abs(r)/(A/1e6),120)` | −1 | 121 |
| 55 | `liq_volume_cv_20` | 20日成交量变异系数 | `std(V,20)/mean(V,20)` | −1 | 20 |
| 56 | `liq_volume_cv_60` | 60日成交量变异系数 | `std(V,60)/mean(V,60)` | −1 | 60 |
| 57 | `liq_volume_ratio_5_20` | 5/20日成交量比 | `mean(V,5)/mean(V,20)` | +1 | 20 |
| 58 | `liq_volume_ratio_20_60` | 20/60日成交量比 | `mean(V,20)/mean(V,60)` | +1 | 60 |
| 59 | `liq_amount_ratio_5_20` | 5/20日成交额代理比 | `mean(A,5)/mean(A,20)` | +1 | 20 |
| 60 | `liq_amount_ratio_20_60` | 20/60日成交额代理比 | `mean(A,20)/mean(A,60)` | +1 | 60 |
| 61 | `liq_zero_volume_20` | 20日零成交记录比例 | `mean(1[V=0],20)` | −1 | 20 |
| 62 | `liq_zero_volume_60` | 60日零成交记录比例 | `mean(1[V=0],60)` | −1 | 60 |
| 63 | `liq_return_volume_corr_20` | 20日收益成交量相关 | `corr(r,V,20)` | +1 | 21 |
| 64 | `liq_return_volume_corr_60` | 60日收益成交量相关 | `corr(r,V,60)` | +1 | 61 |
| 65 | `liq_price_impact_60` | 60日波动/成交额代理 | `std(r,60)/(mean(A,60)/1e6)` | −1 | 61 |

## 估值（15 项）

状态：`awaiting_pit_fundamentals`。

| 序号 | 指标 ID | 含义 | 公式 | 方向 | 最低观察数 |
|---:|---|---|---|---:|---:|
| 66 | `value_earnings_yield` | 盈利收益率 | `NI_TTM / market_cap` | +1 | — |
| 67 | `value_book_to_price` | 账面市值比 | `common_equity / market_cap` | +1 | — |
| 68 | `value_sales_yield` | 营收市值比 | `revenue_TTM / market_cap` | +1 | — |
| 69 | `value_operating_cashflow_yield` | 经营现金流收益率 | `CFO_TTM / market_cap` | +1 | — |
| 70 | `value_free_cashflow_yield` | 自由现金流收益率 | `(CFO_TTM-capex_TTM) / market_cap` | +1 | — |
| 71 | `value_dividend_yield` | 现金股息收益率 | `cash_dividends_TTM / market_cap` | +1 | — |
| 72 | `value_ebit_ev` | EBIT企业价值比 | `EBIT_TTM / EV` | +1 | — |
| 73 | `value_ebitda_ev` | EBITDA企业价值比 | `EBITDA_TTM / EV` | +1 | — |
| 74 | `value_revenue_ev` | 营收企业价值比 | `revenue_TTM / EV` | +1 | — |
| 75 | `value_net_cash_to_cap` | 净现金市值比 | `(cash-total_debt) / market_cap` | +1 | — |
| 76 | `value_net_current_assets_to_cap` | 净流动资产市值比 | `(current_assets-total_liabilities) / market_cap` | +1 | — |
| 77 | `value_tangible_book_to_price` | 有形净资产市值比 | `(common_equity-goodwill-other_intangibles) / market_cap` | +1 | — |
| 78 | `value_retained_earnings_to_cap` | 留存收益市值比 | `retained_earnings / market_cap` | +1 | — |
| 79 | `value_gross_profit_ev` | 毛利企业价值比 | `gross_profit_TTM / EV` | +1 | — |
| 80 | `value_shareholder_yield` | 股东回报收益率 | `(cash_dividends_TTM+buybacks_TTM-share_issuance_TTM) / market_cap` | +1 | — |

## 盈利质量与财务稳健（10 项）

状态：`awaiting_pit_fundamentals`。

| 序号 | 指标 ID | 含义 | 公式 | 方向 | 最低观察数 |
|---:|---|---|---|---:|---:|
| 81 | `quality_roe` | 净资产收益率 | `NI_common_TTM / average_common_equity` | +1 | — |
| 82 | `quality_roa` | 总资产收益率 | `NI_TTM / average_total_assets` | +1 | — |
| 83 | `quality_gross_margin` | 毛利率 | `gross_profit_TTM / revenue_TTM` | +1 | — |
| 84 | `quality_operating_margin` | 营业利润率 | `operating_profit_TTM / revenue_TTM` | +1 | — |
| 85 | `quality_cash_conversion` | 利润现金含量 | `CFO_TTM / NI_TTM; NI_TTM>0` | +1 | — |
| 86 | `quality_accruals` | 应计利润比例 | `(NI_TTM-CFO_TTM) / average_total_assets` | −1 | — |
| 87 | `quality_debt_assets` | 有息负债资产比 | `total_debt / total_assets` | −1 | — |
| 88 | `quality_interest_coverage` | 利息保障倍数 | `EBIT_TTM / interest_expense_TTM` | +1 | — |
| 89 | `quality_current_ratio` | 流动比率 | `current_assets / current_liabilities` | +1 | — |
| 90 | `quality_cash_assets` | 现金资产比 | `cash / total_assets` | +1 | — |

## 成长（10 项）

状态：`awaiting_pit_fundamentals`。

| 序号 | 指标 ID | 含义 | 公式 | 方向 | 最低观察数 |
|---:|---|---|---|---:|---:|
| 91 | `growth_revenue_yoy` | 营收同比增长 | `revenue_TTM/revenue_TTM_1y_ago-1` | +1 | — |
| 92 | `growth_income_yoy` | 净利润同比变化 | `(NI_TTM-NI_TTM_1y_ago)/abs(NI_TTM_1y_ago)` | +1 | — |
| 93 | `growth_eps_yoy` | 每股盈利同比变化 | `(EPS_TTM-EPS_TTM_1y_ago)/abs(EPS_TTM_1y_ago)` | +1 | — |
| 94 | `growth_gross_profit_yoy` | 毛利同比变化 | `(gross_profit_TTM-gross_profit_TTM_1y_ago)/abs(gross_profit_TTM_1y_ago)` | +1 | — |
| 95 | `growth_cashflow_yoy` | 经营现金流同比变化 | `(CFO_TTM-CFO_TTM_1y_ago)/abs(CFO_TTM_1y_ago)` | +1 | — |
| 96 | `growth_book_equity_yoy` | 净资产同比增长 | `common_equity/common_equity_1y_ago-1` | +1 | — |
| 97 | `growth_assets_yoy` | 资产同比增长（谨慎扩张假设） | `total_assets/total_assets_1y_ago-1` | −1 | — |
| 98 | `growth_operating_profit_yoy` | 营业利润同比变化 | `(operating_profit_TTM-operating_profit_TTM_1y_ago)/abs(operating_profit_TTM_1y_ago)` | +1 | — |
| 99 | `growth_dividends_yoy` | 股息同比增长 | `cash_dividends_TTM/cash_dividends_TTM_1y_ago-1` | +1 | — |
| 100 | `growth_profit_margin_change` | 净利率同比变化 | `NI_TTM/revenue_TTM-NI_TTM_1y_ago/revenue_TTM_1y_ago` | +1 | — |


