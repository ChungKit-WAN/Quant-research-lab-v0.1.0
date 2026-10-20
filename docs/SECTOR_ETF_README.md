> Historical snapshot / 历史快照：下文的“当前”和“两项目未合并”指原研究记录保存时的状态。现已抽取计算核心供统一框架使用，见 [主 README](../README.md)。原数据库、发行商材料及历史报告未随代码分发；目录名是通用占位。原文已备份到本机 outputs/local_document_archive。

# Fixed 11-Sector ETF Risk Allocation Research / 固定 11 只行业 ETF 风险配置研究

[English](#english) | [中文](#chinese)

<a id="english"></a>

## English

**Risk allocation research with a fixed set of 11 sector ETFs**

Current status: **All five engineering stages in this round are complete, including the calculation pipeline, research reports, and conditional dividend scenario. Independent data certification and statistical inference remain incomplete.**

This document describes the active project at `legacy-etf-project` and can be saved there as `README.md`. `quant-research-lab` contains a different version of the individual-stock indicator program. The two projects have not been merged, and their entry points must not be mixed.

The current research compares three risk allocation methods: equal weight, minimum variance using sample covariance, and minimum variance using covariance shrunk toward a constant-correlation target. The earlier MSFT financial-factor and stock-selection work is on hold. These ETF results do not establish that the stock-selection factor-screening method has been validated.

### Current progress

The “five stages” refer to this round of ETF engineering. They do not mean that all research work, including independent verification and statistical inference, is complete.

| Stage | Work | Current status and outputs |
|---|---|---|
| 1 | Data and fixed experiment protocol | Complete: 11 ETFs, price and return matrices, period definitions, and fixed parameters |
| 2 | Rolling allocation and trade accounting | Complete: 69 rebalances and 1,442 daily NAV records per strategy; 207 rebalances across the three strategies |
| 3 | Baseline performance and research report | Complete: 9 sets of period metrics, NAV/drawdown charts, and sector-weight charts |
| 4 | Conditional dividend scenario | Complete: 343 dividend events replaced; 207 target-weight vectors, 138 minimum-variance solves, and the complete trading and performance paths recomputed |
| 5 | Report supplement and consolidation | Complete: baseline–scenario differences, 6 exceptions to the amount hypothesis, and completed and remaining work; this README adds operating instructions |

The latest saved supplement contains 9 baseline metric rows and 9 sensitivity metric rows, with all 12 reported metric rankings unchanged. Full strategy-sensitivity replay, verification of the original baseline charts, and saved-content read-back all passed.

### View the results first

- Current research supplement：`storage/etf_reports/sector_etf_sensitivity_report_1c9fe39b1a12499a87b523b33addffed/index.html`（仅原工程本地存档，未随仓库分发）
- Supplement manifest：`storage/etf_reports/sector_etf_sensitivity_report_1c9fe39b1a12499a87b523b33addffed/manifest.json`（仅原工程本地存档，未随仓库分发）
- Original baseline research report：`storage/etf_reports/sector_etf_research_report_1415eacdf3ce4f6aa99d122402b27116/index.html`（仅原工程本地存档，未随仓库分发）

Canonical JSON SHA-256 of the supplement manifest:

```text
18c1f746bb9dab7f0968945e928cb3ee78085da2cdeadfa50c7432342dc660ed
```

A new run creates a new report directory named with a UUID. Its path and report SHA change with metadata such as the generation time. The links above point to the version checked for this README; they do not automatically select the latest report.

### Fixed research conventions

| Item | Setting |
|---|---|
| ETFs | XLB, XLC, XLE, XLF, XLI, XLK, XLP, XLRE, XLU, XLV, XLY |
| Data range | From 2019-01-01 through 2026-10-01 exclusive; daily USD data |
| Source | Yahoo Finance, preserved as table snapshots parsed by yfinance |
| Trading calendar | XNYS regular sessions, used as a calendar proxy for NYSE Arca ETFs |
| Warmup | 2019–2020; 504 return rows |
| Development period | 2021–2023; 753 return rows |
| Holdout period | 2024 through 2026-09-30; 689 return rows |
| Risk estimation | The most recent 504 return observations through and including the signal-session close; sample covariance and Ledoit–Wolf covariance shrinkage toward a constant-correlation target |
| Weight constraints | Long only, target weights sum to 1, 25% target cap per asset, fractional synthetic units allowed |
| Timing | Signal after the month-end close; trade at the next session's close; new positions earn returns only after the execution close |
| Costs | 5 bp of each buy or sell notional, including initial entry; costs funded through self-financing trades |
| Between rebalances | Synthetic units remain constant while weights drift with prices; the 25% cap applies to rebalance targets, not daily actual weights |
| Period transitions and termination | No position or NAV reset at the development/holdout boundary; no forced terminal liquidation; assumed cash return of 0 |
| Annualization | 252 trading sessions; CVaR is the mean of the worst 5% probability mass of daily losses |

The initial signal is 2020-12-31, the first execution is 2021-01-04, and the first return earned by the new positions is recorded on 2021-01-05. The first execution day includes only the entry cost; returns before that day's close are not assigned to the new positions.

The matrices contain 1,947 × 11 prices and 1,946 × 11 returns, with 21,417 price records in total. The full research period has 1,442 daily NAV records per strategy, includes the initial entry cost, and excludes warmup. The 2026-09-30 signal would execute on 2026-10-01, outside the sample; no target weights or trades were computed for that event in this round.

Return inputs are changes in the provider's adjusted closing prices. The trading ledger uses synthetic wealth based on those adjusted prices. It is not an independently verified ledger of raw shares and cash-dividend reinvestment. Dividends or split multipliers must not be applied a second time.

### Observed results and evidence limits

In this sample's holdout period, sample minimum variance has lower volatility and daily CVaR than the other two strategies; equal weight has the highest net CAGR; and shrinkage minimum variance has a slightly lower maximum drawdown than sample minimum variance. These metrics show trade-offs, and the comparison remains descriptive.

All 343 dividend dates in the currently archived issuer material match the provider records, as do the 5 splits explicitly listed in the announcement. The hypothesis “round to three decimal places, then convert for the known split” accounts for 337/343 events. The remaining 6 are retained as exceptions. This fit does not confirm the provider's rounding rule.

All 343 unrounded issuer DIVIDEND amounts were used in the sensitivity scenario under the stated split-unit hypothesis. Blank capital-gain fields remain missing. The scenario preserves the original provider adjustment residuals; it neither independently certifies prices nor applies a data correction.

| Strategy | Maximum target-weight change, bp | Full research period terminal NAV relative change, bp | Holdout growth-factor ratio change, bp |
|---|---:|---:|---:|
| Equal weight | 0.000000 | -0.104920 | +0.017163 |
| Sample minimum variance | 0.328617 | -0.007252 | +0.115887 |
| Shrinkage minimum variance | 0.293657 | -0.011465 | +0.107405 |

1 bp = 0.0001 in decimal units = 0.01 percentage point. The full research period terminal NAV relative change is “scenario terminal NAV / baseline terminal NAV − 1.” The holdout growth-factor ratio change first divides each path by its own opening holdout NAV, then compares the resulting growth factors. The former includes the accumulated development-period effect, so the two columns may have different signs. Neither is a CAGR difference.

This conditional scenario left all 12 rankings unchanged across three periods and four main performance metrics. It is a conditional post-hoc scenario examined after viewing performance, not evidence of general robustness, statistical significance, or a new unseen holdout validation.

The user stated, in translation from Chinese, “I had not seen the holdout comparison results for these strategies.” This statement was recorded after the results were generated and is retained as a user self-report, without independent verification. The currently archived versions also do not establish availability at historical decision times.

### Modules and storage

| File | Responsibility |
|---|---|
| `etf_experiment.py` | Fixed universe, periods, risk estimation, costs, and evaluation protocol |
| `etf_data.py` | ETF price collection and adjustment-consistency audit |
| `etf_dataset.py` | Price, return, and period datasets built from saved audit results |
| `etf_schedule.py` | Month-end signals, execution dates, and rolling-window schedule |
| `risk_models.py` | Sample covariance and shrinkage toward a constant-correlation target |
| `portfolio.py` | Capped minimum-variance optimization and certificate checks |
| `etf_targets.py` | Rolling target weights for the three strategies |
| `execution.py` | Trades, costs, and self-financing rebalances |
| `backtest.py` | Continuous synthetic wealth, position, and cash paths |
| `performance.py` | Period volatility, CAGR, drawdown, CVaR, costs, and sector-weight statistics |
| `etf_evidence.py` | Issuer-source archives, XLE event comparisons, and precision diagnostics |
| `etf_action_audit.py` | Issuer/provider event comparisons for all 11 ETFs |
| `etf_sensitivity.py` | Dividend-return scenario and recomputation of covariance, weights, trades, and performance |
| `etf_report.py` | Baseline report and sensitivity supplement export |
| `database.py` | Database, canonical JSON, fingerprinting, and related support |
| `factors.py` / `factor_dataset.py` | Earlier individual-stock factor formulas and datasets; separate from the current ETF experiment |

```text
storage/
  sector_etf_raw.sqlite       Raw ETF snapshots and daily bars
  etf_reports/               Protocol, audit, returns, weights, NAV, performance, and HTML reports
  etf_evidence/              Issuer sources, event comparisons, precision diagnostics, and sensitivity reports
```

JSON reports store `report` and `canonical_sha256`. HTML report manifests also record hashes of the file bytes. Replay uses pinned source fingerprints and checks code, data, and calculated results; ordinary timestamp differences are handled according to the existing functions. A canonical JSON fingerprint is not the same as a SHA computed directly over all bytes of the JSON file.

The modules currently expose Python functions, without a unified end-to-end `main.py` or CLI. Running `python etf_report.py` directly does not generate a report. The command below requires the saved database, source archives, upstream JSON reports, and original baseline images. It is not a one-command script that downloads data and builds every artifact from scratch.

### Revalidate and generate a supplement

Run the following in PowerShell using the existing environment:

```powershell
Set-Location -LiteralPath 'legacy-etf-project'

@'
import py_compile
py_compile.compile("etf_report.py", doraise=True)
print("Syntax check: passed")

from etf_report import build_sector_etf_sensitivity_report

result = build_sector_etf_sensitivity_report(
    "storage/etf_evidence/"
    "sector_etf_strategy_sensitivity_f8abe35a322c43f7842a3d6ff90579f1.json",
    expected_strategy_sha256=(
        "dfced5dbb3ba2d62522461796ed9d17d60489c45c45e979c69e8e351d4035a9c"
    ),
)
for key, value in result.items():
    print(f"{key}: {value}")
'@ | python -
```

This call does not download prices again. It fully replays the strategy sensitivity from pinned snapshots, checks the original baseline charts, and creates a new UUID directory under `storage/etf_reports/`. Open the returned `html_file` to view the new report. The original reports are retained.

Key expected output:

```text
baseline_metric_rows: 9
sensitivity_metric_rows: 9
rankings_unchanged: 12
full_strategy_sensitivity_replay_verified: True
baseline_artifacts_verified: True
saved_content_verified: True
eligibility_effect: unchanged
backtest_ready: False
```

If a fingerprint or replay differs, check the actual interpreter, code, source files, and paths. Do not merely replace the expected SHA or remove validation to force a pass. Upstream reports contain absolute paths; moving a few JSON files does not make the project replayable in a new location.

### Environment snapshot

The following core versions were read from the active project's runtime environment. This is a core-package snapshot, not a lockfile containing all transitive dependencies. It must not be mixed with the older directory's `.venv` and `requirements.txt`.

| Component | Version |
|---|---|
| Python | 3.13.15 |
| NumPy | 2.5.3 |
| pandas | 3.0.6 |
| yfinance | 1.7.0 |
| exchange-calendars | 4.13.2 |
| openpyxl | 3.1.5 |
| matplotlib | 3.11.2 |

The existing archives correspond to this calculation environment. Changing versions or code used in replay may cause implementation fingerprints or numerical results to differ and should be treated as an environment or implementation change. Viewing an already generated HTML report does not require these Python packages.

### Remaining work

#### Independent evidence still needed

- [ ] Share-unit basis and rounding rules for dividend amounts, and the sources of the 6 exceptions.
- [ ] Meaning of blank capital-gain fields, corporate-action completeness, and independent price checks.
- [ ] Historical published versions and evidence of availability at historical decision times. Downloading today's files again cannot replace earlier published versions.

`backtest_ready=False` is a retained conservative flag. It does not indicate a program error or unfinished calculations, and it is not an eligibility decision automatically performed by this README. `adjusted_return_basis_verified`, `corporate_actions_independently_verified`, `historical_data_availability_verified`, and `full_universe_pit_eligible` all retain their original False values. This conditional study of fixed ETFs does not require reconstructing the historical stock universe of the entire market.

#### Optional research and engineering extensions

- [ ] Statistical uncertainty of metric differences; no significance testing has been performed.
- [ ] Other cost, window, or sample scenarios, recorded separately as new exploratory analyses rather than using already seen holdout results to claim prior validation.
- [ ] A unified execution entry point, complete environment locking, portable source paths, and an entry point for regression checks.
- [ ] If stock-selection factor research resumes, maintain its literature, factor definitions, and validation protocol separately; do not directly extrapolate these ETF results.

These extensions do not change the completed status of the five engineering stages in this round. Update the README, HTML reports, and source manifests together when substantive changes occur, while retaining this fixed result version.

---

<a id="chinese"></a>

## 中文

**固定 11 只行业 ETF 风险配置研究**

当前状态：**本轮五个工程环节已完成，包括计算主链、研究报告和分红条件情景。独立数据认证与统计推断尚未完成。**

本说明对应实际项目目录 `legacy-etf-project`，可保存为该目录的 `README.md`。`quant-research-lab` 保留的是另一版个股指标程序，两者尚未合并，运行入口不能混用。

当前研究比较等权、样本协方差最小方差、常相关目标收缩协方差最小方差三种风险配置方法。原 MSFT 财务因子及选股方向暂缓，本实验的结果不等同于选股因子筛选方法已获验证。

### 目前到哪一步

“五步”指本轮 ETF 工程的五个环节，不代表独立验证、统计推断等全部研究工作均已完成。

| 步骤 | 工作 | 当前状态与产物 |
|---|---|---|
| 1 | 数据与固定实验方案 | 已完成：11 只 ETF、价格及收益矩阵、时间划分和固定参数 |
| 2 | 滚动配置与交易记账 | 已完成：每策略 69 次调仓、1,442 日净值；三策略共 207 次调仓 |
| 3 | 基线绩效和研究报告 | 已完成：9 组分期绩效、净值/回撤图和行业权重图 |
| 4 | 分红条件情景 | 已完成：替换 343 笔分红，重算 207 组目标权重、138 次最小方差求解及完整交易绩效 |
| 5 | 报告补充与汇总 | 已完成：基线与情景差异、6 笔金额假设例外、已完成与剩余工作；本 README 补充运行说明 |

最近保存的补充报告有基线绩效 9 行、敏感性绩效 9 行、12 项指标排序未改变；完整策略敏感性重放、原基线图核对和保存回读均通过。

### 先看结果

- 当前研究补充报告：`storage/etf_reports/sector_etf_sensitivity_report_1c9fe39b1a12499a87b523b33addffed/index.html`（仅原工程本地存档，未随仓库分发）
- 补充报告 manifest：`storage/etf_reports/sector_etf_sensitivity_report_1c9fe39b1a12499a87b523b33addffed/manifest.json`（仅原工程本地存档，未随仓库分发）
- 原基线研究报告：`storage/etf_reports/sector_etf_research_report_1415eacdf3ce4f6aa99d122402b27116/index.html`（仅原工程本地存档，未随仓库分发）

补充报告 manifest 的规范 JSON SHA-256：

```text
18c1f746bb9dab7f0968945e928cb3ee78085da2cdeadfa50c7432342dc660ed
```

新运行会创建新的 UUID 报告目录，路径与报告 SHA 会随生成时间等元数据改变。以上链接固定指向本 README 核对过的版本，不是自动选择“最新”的入口。

### 固定研究口径

| 项目 | 设定 |
|---|---|
| ETF | XLB、XLC、XLE、XLF、XLI、XLK、XLP、XLRE、XLU、XLV、XLY |
| 数据范围 | 2019-01-01 起，2026-10-01 不含；美元日线 |
| 来源 | Yahoo Finance，经 yfinance 解析的表级快照 |
| 交易日历 | XNYS 常规交易日，作为 NYSE Arca ETF 的日历代理 |
| 预热期 | 2019—2020 年，504 行收益 |
| 开发期 | 2021—2023 年，753 行收益 |
| 留出期 | 2024 年至 2026-09-30，689 行收益 |
| 风险估计 | 截至每次信号日收盘（含当日）的最近 504 行收益；样本协方差和 Ledoit–Wolf 常相关目标收缩协方差 |
| 权重约束 | 只做多、目标权重和为 1、单资产目标上限 25%，允许分数合成单位 |
| 时间顺序 | 月末收盘后发出信号，下一交易日收盘交易，新仓从交易收盘之后承担收益 |
| 费用 | 每笔买入或卖出成交额的 5 bp，包含首次入场费用；自融资扣费 |
| 持有期间 | 合成单位不变、权重随价格漂移；25% 约束针对调仓目标，不针对每日实际权重 |
| 跨期与结束 | 开发期进入留出期不重置持仓或净值；期末不强制清仓；现金收益假设为 0 |
| 年化 | 252 个交易日；CVaR 为日损失最差 5% 概率质量的均值 |

初始信号为 2020-12-31，首次执行为 2021-01-04，首次新仓收益记在 2021-01-05。首次执行日只扣入场费用，不把该日收盘前的收益计入新仓。

数据矩阵为 1,947 × 11 个价格、1,946 × 11 个收益；价格记录共 21,417 行。全研究期净值为每策略 1,442 日，包含初始入场费用、不包含预热期。2026-09-30 信号对应的 2026-10-01 执行超出样本，本轮未计算该期目标权重或交易。

收益输入为供应商复权收盘价的变化率，交易账本使用合成复权价格财富口径。它不是逐笔原始份额、现金分红再投资的独立核实账本；不得再额外加一次分红或拆分倍数。

### 已观察到的结果与证据边界

在本样本留出期，样本最小方差的波动率与日 CVaR 低于另外两种策略，等权的净 CAGR 最高，收缩最小方差的最大回撤略低于样本最小方差。指标存在取舍，目前只作描述性比较。

当前归档发行商资料与供应商记录的 343 个分红日期全部对应，公告明确列出的 5 次拆分对应。“先取三位小数再按已知拆分换算”的假设解释 337/343 笔，剩余 6 笔保留为例外；拟合结果不等于已确认供应商取整规则。

全部 343 笔未取整发行商 DIVIDEND 金额，在既定拆分单位假设下进入了敏感性情景。资本利得空白仍为缺失。情景保留原供应商调整残差，没有独立认证价格或实施数据纠错。

| 策略 | 最大目标权重变化 bp | 全研究期末净值相对变化 bp | 留出期自身净增长比变化 bp |
|---|---:|---:|---:|
| 等权 | 0.000000 | -0.104920 | +0.017163 |
| 样本最小方差 | 0.328617 | -0.007252 | +0.115887 |
| 收缩最小方差 | 0.293657 | -0.011465 | +0.107405 |

1 bp = 0.0001（小数）= 0.01 个百分点。全研究期末净值相对变化为“情景期末净值 / 基线期末净值 − 1”；留出期自身净增长比先将两条路径分别除以各自留出期初净值，再比较增长因子。前者包含开发期的累积影响，两列符号可以不同，两者都不是 CAGR 差值。

本次条件情景未改变三个期间、四项主要绩效指标的 12 项排序。它是查看绩效后的事后敏感性实验，不构成一般稳健性、统计显著性或新的未见留出验证。

用户已声明“未看过这些策略的留出期比较结果”。该声明在结果生成后记录，作为用户自述保留，未独立核验。当前归档版本也不证明历史决策时点的可得性。

### 模块与存储

| 文件 | 职责 |
|---|---|
| `etf_experiment.py` | 固定股票池、期间、风险估计、费用及评估协议 |
| `etf_data.py` | ETF 价格采集与复权一致性审计 |
| `etf_dataset.py` | 基于已保存审计结果构建价格、收益及期间数据集 |
| `etf_schedule.py` | 月末信号、执行日期与滚动窗口计划 |
| `risk_models.py` | 样本协方差与常相关目标收缩估计 |
| `portfolio.py` | 有权重上限的最小方差求解与证书检查 |
| `etf_targets.py` | 滚动窗口的三策略目标权重 |
| `execution.py` | 成交、费用与自融资调仓 |
| `backtest.py` | 连续的合成财富、持仓及现金路径 |
| `performance.py` | 分期波动、CAGR、回撤、CVaR、费用与行业权重统计 |
| `etf_evidence.py` | 发行商来源归档、XLE 事件比较及精度诊断 |
| `etf_action_audit.py` | 全部 11 只 ETF 的发行商与供应商事件比较 |
| `etf_sensitivity.py` | 分红收益情景，以及协方差、权重、交易、绩效的重算 |
| `etf_report.py` | 基线报告与敏感性补充报告导出 |
| `database.py` | 数据库及规范 JSON/指纹等基础支持 |
| `factors.py` / `factor_dataset.py` | 原个股因子公式与数据集工作；与当前 ETF 实验分开 |

```text
storage/
  sector_etf_raw.sqlite       ETF 原始快照与日线
  etf_reports/               方案、审计、收益、权重、净值、绩效及 HTML 报告
  etf_evidence/              发行商来源、事件比较、精度诊断与敏感性报告
```

JSON 报告保存 `report` 与 `canonical_sha256`，HTML 报告的 manifest 还记录文件字节指纹。重放使用固定来源指纹并核对代码、数据和计算结果；普通时间戳差异按已有函数规则处理。规范 JSON 指纹与“直接对整个 JSON 文件字节求 SHA”不是同一口径。

目前模块主要提供 Python 函数，没有统一的全流程 `main.py` 或 CLI。直接执行 `python etf_report.py` 不会自动生成报告。下述命令依赖已经保存的数据库、来源档案、上游 JSON 和原基线图片，不是从零下载并建立全部产物的一键脚本。

### 重新验证并生成补充报告

在 PowerShell 使用当前已有环境执行：

```powershell
Set-Location -LiteralPath 'legacy-etf-project'

@'
import py_compile
py_compile.compile("etf_report.py", doraise=True)
print("Syntax check: passed")

from etf_report import build_sector_etf_sensitivity_report

result = build_sector_etf_sensitivity_report(
    "storage/etf_evidence/"
    "sector_etf_strategy_sensitivity_f8abe35a322c43f7842a3d6ff90579f1.json",
    expected_strategy_sha256=(
        "dfced5dbb3ba2d62522461796ed9d17d60489c45c45e979c69e8e351d4035a9c"
    ),
)
for key, value in result.items():
    print(f"{key}: {value}")
'@ | python -
```

该调用不重新下载行情，而是从固定快照完整重放策略敏感性、核对原基线图，并在 `storage/etf_reports/` 下新建 UUID 目录。以输出的 `html_file` 打开本次报告；原报告保留。

关键预期输出：

```text
baseline_metric_rows: 9
sensitivity_metric_rows: 9
rankings_unchanged: 12
full_strategy_sensitivity_replay_verified: True
baseline_artifacts_verified: True
saved_content_verified: True
eligibility_effect: unchanged
backtest_ready: False
```

遇到指纹或重放不一致时，检查实际解释器、代码、来源文件和路径。不要仅替换期望 SHA 或删除校验来使其通过。上游报告保存了绝对路径；迁移项目时不能只移动几个 JSON 文件就假定能够重放。

### 环境快照

本次读取实际项目运行环境得到如下核心版本。这是核心包快照，不是包含全部传递依赖的锁文件；与旧目录的 `.venv` 和 `requirements.txt` 不应混用。

| 项目 | 版本 |
|---|---|
| Python | 3.13.15 |
| NumPy | 2.5.3 |
| pandas | 3.0.6 |
| yfinance | 1.7.0 |
| exchange-calendars | 4.13.2 |
| openpyxl | 3.1.5 |
| matplotlib | 3.11.2 |

已有归档对应上述计算环境。更换版本或改变参与重放的代码，可能触发实现指纹或数值结果不一致，应作为环境/实现变更处理。仅查看已生成 HTML 不需要安装这些 Python 包。

### 剩余工作

#### 待补的独立证据

- [ ] 分红金额的份额单位、取整依据与 6 笔例外来源。
- [ ] 资本利得空白的含义、公司行动完整性与独立价格核对。
- [ ] 历史发布版本和历史时点可得性证据。重新下载今天的文件不能替代过去的发布版本。

`backtest_ready=False` 是沿用的保守标志，不是程序错误或计算未完成，也不是本 README 自动运行的准入判定。`adjusted_return_basis_verified`、`corporate_actions_independently_verified`、`historical_data_availability_verified`、`full_universe_pit_eligible` 均保持原来的 False。本固定 ETF 条件研究不以重建全市场历史股票池为前提。

#### 可选的后续研究与工程扩展

- [ ] 指标差异的统计不确定性；当前未做显著性检验。
- [ ] 其他费用、窗口或样本情景，作为新的探索分析另行记录，不用已见留出结果反向宣称预先验证。
- [ ] 统一执行入口、完整环境锁定、可迁移的来源路径及回归检查入口。
- [ ] 若恢复选股因子研究，另行维护文献、因子定义与验证协议，不把本 ETF 结果直接外推。

这些扩展不改变本轮五个工程环节已完成的状态。README、HTML 报告和来源 manifest 应在后续实质变化时同步更新，且保留本次固定结果版本。
