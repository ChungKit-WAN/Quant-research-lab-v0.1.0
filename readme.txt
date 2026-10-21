Quant Research Lab

A shared monthly research framework for sector ETF allocation and stock-factor selection.

Developed collaboratively by a four-member team.

We study how covariance estimation affects sector ETF allocation and how price/volume factor rankings affect stock portfolios. Both strategy families use the same rebalancing, transaction-cost, and portfolio-accounting conventions, making methodological differences easier to examine. Engineering reproducibility and predictive performance are evaluated separately.

Current version: v0.11 (package version 0.11.0). This includes the research-validation milestone previously discussed as v0.1.1, eleven sector pages and portable refresh. Daily decisions in v1.0, hourly decisions in v2.0, and AI-assisted minute/second decisions in v3.0 remain future work in the version roadmap (docs/VERSION_ROADMAP.md).

One-click reports on a new computer

English is the primary language for the interface, reports, code identifiers, CLI messages and documentation. Chinese companion reports remain available from the language switch. On the overview, ETF backtest or stock backtest page, click an ETF such as XLK to open its sector stock rankings. The linked page shows the configured research sample; it does not claim to contain the fund’s complete or historical holdings.

On Windows, extract the source bundle and double-click START_V011.cmd. It verifies the bootstrap download, installs project-local Python and dependencies, downloads current prices, recalculates all reports, and opens the result. It does not depend on the original computer's environment. Internet access to the official software sources and Yahoo is required; errors retain logs and never count as a successful refresh. macOS/Linux have bash START_V011.sh, authored but not tested on those operating systems.

- Overview and eleven sector pages, with five editable sample stocks per sector (55 total). This is not the whole market or historical index membership.
- All 100 factor definitions, formulas, directions and status fields are visible. The 65 price/volume factors have calculated values; 35 financial factors remain unavailable pending point-in-time fundamentals. Sort any metric ascending or descending; missing values are always last and unranked. Display sorting does not change the strategy.
- English dashboards with Chinese companions, ETF/stock backtests and validation reports, with CSV/JSON exports. All computed performance metrics and asset weight statistics appear in the backtest reports.
- Each launch resolves the clock again: five research years, three earlier warmup years and a trailing 24-month chronological holdout. Only completed New York sessions plus a two-hour data-source buffer are used; rankings use fully completed exchange-calendar months.
- Nine predefined experiments cover 5/10/20 bp costs, holdings count, ranking windows and removal of each factor group's score contribution. Every success and failure is saved. A chronological holdout is not certified unseen data.

Edit configs/refresh.json to change the sample and windows. Each run is preserved in outputs/v011/runs/<run-id>/; outputs/v011/report.html points to the latest fully successful run. Raw source tables, SQLite batches, price samples, calendar coverage, experiment plans and SHA-256 hashes are retained. This downloads prices and generates research reports; it does not download company annual reports or SEC filing text.

With Python installed, run python -m quant_research refresh --open. Optional --as-of YYYY-MM-DD reproduces a historical cutoff; omitting it uses the current clock. Explicit offline demonstrations use refresh --demo --output outputs/v011_demo and are labelled synthetic. refresh --prices path.csv requires all configured stocks and eleven ETFs. See the portable guide (docs/PORTABLE_V011.md).

Language: English (primary) · 中文辅助 (README_ZH.md)

Reading guide: Quick start (START_HERE.md) · English plain text (readme.txt) · Methodology (docs/METHODOLOGY.md) · Factor catalog (docs/FACTOR_CATALOG.md) · Validation (docs/VALIDATION.md) · Roadmap (docs/VERSION_ROADMAP.md) · GitHub upgrade guide (docs/GITHUB_UPDATE_V011.md)

Implemented scope

| Strategy family | Inputs and methods | Shared capabilities |
| Sector ETFs | A fixed universe of 11 sector ETFs; equal weight, sample-covariance minimum variance, and constant-correlation shrinkage minimum variance | Session validation, month-end signals, execution at the next session's close, positions/cash/cost ledger, daily NAV, and performance metrics |
| Stocks | Daily OHLCV and adjusted close; price/volume factor ranking followed by equal weighting of the highest-ranked stocks | The ETF core's monthly schedule and portfolio accounting, a unified command-line interface, and report exports |

The ETF family compares equal_weight, sample_min_variance, and shrinkage_min_variance. Its default universe is XLB, XLC, XLE, XLF, XLI, XLK, XLP, XLRE, XLU, XLV, XLY.

The stock family compares equal_weight across the configured universe with multifactor_top_n, which equally weights the top N stocks. The v0.11 refresh uses 55 sample stocks. The older demo/run --family stocks keeps the ten-stock example AAPL, MSFT, GOOGL, AMZN, NVDA, META, JPM, JNJ, XOM, PG. These are fixed research samples, not historical index membership. Both strategies rebalance monthly and incur transaction costs. The fixed dates in the manual configurations below apply to demo/run; refresh derives dates from its rolling-window settings.

The factor catalog contains 100 candidates, of which 65 are implemented: 20 momentum, 10 reversal, 15 risk, and 20 liquidity factors. The remaining 35 candidates—15 value, 10 quality, and 10 growth factors—require financial data with historical availability timestamps. They are not implemented and are not replaced with zeros. See the factor catalog (docs/FACTOR_CATALOG.md). Factor directions and group weights are hypotheses to test; the number of factors does not establish predictive value.

The default stock pipeline requires all 65 factors to be valid, adjusts their directions, computes cross-sectional percentiles, averages within groups, and combines momentum/reversal/risk/liquidity with weights of 30%/10%/40%/20%. It then averages ranking percentiles over three consecutive months, ranks again, and equally weights the top four stocks. Final ties are broken by ascending ticker. Formulas and the selection diagram are in the methodology (docs/METHODOLOGY.md).

“Monthly” describes the decision frequency. Daily observations support risk estimation and portfolio accounting. The ledger holds synthetic fractional units based on adjusted prices and includes purchase, sale, and initial-entry costs. It is not an independently certified ledger of raw share counts and cash dividends.

Shared workflow

Shared workflow:
1. Price CSV or synthetic demo
2. Validate fields, universe, and sessions
3. Build month-end signals and the next-session execution schedule
4. Generate target weights in two branches:
   - ETFs: return window and covariance estimates → equal weight and two minimum-variance methods
   - Stocks: 65 factors and consecutive monthly rankings → universe equal weight and Top-N
5. Feed both branches into the common target-weight interface
6. Apply the shared positions, cash, and cost ledger
7. Compute daily NAV and period metrics
8. Export English reports with Chinese companions, CSV, JSON, and the hash manifest

Both research branches feed target weights into evaluate_targets, sharing execution and accounting. Monthly decisions still use daily observations.

Quick start

Python 3.11+ is required; local validation and the CI configuration use Python 3.13. Initial dependency installation may require internet access. After installation, demos need neither market-data downloads nor a market-data account.

Run these commands from the project root in Windows PowerShell. Activation scripts are not required:

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\python.exe -m quant_research demo --output outputs/demo
.\.venv\Scripts\python.exe -m quant_research demo --family stocks --output outputs/stock_demo

On macOS/Linux:

python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/python -m quant_research demo --output outputs/demo
.venv/bin/python -m quant_research demo --family stocks --output outputs/stock_demo

In later examples, python means the interpreter in this environment. You can keep using its full path. After activating the environment, quant-research can replace python -m quant_research.

Both demos generate deterministic synthetic prices locally. Open the printed report.html path in a browser to view the results. The output directory must be new or empty to preserve earlier experiments. Each demo saves demo_prices.csv, which can be passed to run --prices; it remains synthetic data. Synthetic results validate the software pipeline and are not evidence of market performance, strategy effectiveness, or investment returns.

The unified interface generates a Chinese report, report_zh.html, and an English report, report_en.html, with localized headings, charts, tables, metric explanations, methodology, and evidence limitations. report.html opens the English report by default; use the language link to switch to Chinese. Both reports use the same computed results; CSV and JSON field names remain in English for programmatic use.

The validated Windows/Python 3.13 dependency snapshot is in requirements-lock-py313-windows.txt. To reproduce that environment, run python -m pip install -r requirements-lock-py313-windows.txt, then python -m pip install . --no-deps. Other platforms require their own validation. The standard installation above is also supported.

Bring your own data

run reads an existing CSV and does not download market data. Obtain consistently defined data that you have permission to use. The legacy download and snapshot pipeline has a separate entry point.

ETF input is a long-form CSV with required columns date,ticker,adj_close; dates use YYYY-MM-DD. For example:

date,ticker,adj_close
2020-12-30,XLB,70.12
2020-12-30,XLC,65.87

This fragment illustrates the format only and is insufficient for a backtest. Input tickers must match the configuration exactly, with one row per date/ticker and observations for every regular XNYS session across the input interval. By default, at least 505 price observations through the initial signal date are needed to form 504 return observations.

python -m quant_research run --family etf --prices prices.csv --config configs/sector_monthly.json --output outputs/etf
python -m quant_research run --family stocks --prices stock_prices.csv --config configs/stock_monthly.json --top-n 4 --ranking-window 3 --output outputs/stocks

Stock input requires date,ticker,open,high,low,close,adj_close,volume. Prices must be valid and volume must be nonnegative. Do not conceal missing sessions with filled or copied prices. The unified backtest uses the regular XNYS session calendar, including as a session proxy for ETFs. The legacy Hong Kong ranking entry point remains in rank_report.py; this US backtest calendar should not be applied directly to that market.

See the ETF configuration (configs/sector_monthly.json) and stock configuration (configs/stock_monthly.json). The root-level config.json belongs to the legacy pipeline and is not used by the unified backtest commands.

| Parameter | Default | Meaning and constraint |
| tickers | ETF or stock universe listed above | At least two unique tickers; must match the CSV exactly |
| lookback | 504 | Number of return observations; must exceed the asset count. Stocks also require their own factor warm-up periods and consecutive ranking months |
| research_start | 2021-01-01 | Must be the first calendar day of a month; the initial signal uses the previous month's last session |
| holdout_start | 2024-01-01 | Must follow the research start; splits report periods but does not establish an unseen test set |
| cost_bps | 5.0 | Both families charge 5 bp on purchases and sales: 0.05% of each side's notional |
| max_weight | 0.25 | Per-asset target-weight cap; must be between 1 / asset_count and 1 |
| initial_cash | 1.0 | Positive starting capital; the default supports normalized presentation |
| --top-n | 4 | Stocks only; no greater than the universe size, with 1 / top_n <= max_weight |
| --ranking-window | 3 | Stocks only; at least one consecutive valid month, including the current signal month |

Stock group weights can currently be supplied through the Python interface; the unified CLI has no corresponding option. Changing the shared lookback does not shorten the calculation windows of individual factors.

Signal and execution timing

Signal and execution timing:
1. Month-end close t: use historical information through t to set target weights.
2. Before the execution close: old holdings earn the pre-trade returns.
3. At the next session's close: rebalance and pay transaction costs.
4. After the execution close: new holdings begin to earn returns.
5. On subsequent sessions: mark positions to market until the next rebalance.

Before the first trade, the portfolio holds cash with zero interest. The initial execution day incurs entry costs only; new holdings receive no pre-execution return. The next trading session need not be the next calendar day.

- Signals are computed after month-end close and executed at the next session's close. New positions receive only subsequent returns. A final signal without an execution session inside the sample produces no trade.
- Strategies are long-only, target weights sum to one, and synthetic fractional units are permitted. Weight caps apply to rebalancing targets; price drift can move actual weights beyond those targets.
- Both families charge 5 bp by default on each purchase or sale, including the initial entry. Trades pay their own costs through self-financing accounting. Cash earns zero interest.
- Report-period splits do not reset positions or NAV, and the final sample date does not force liquidation. Compare costs, returns, and risk under consistent conventions.
- Adjusted prices already reflect the provider's adjustments, so dividends and splits are not applied again. Historical data revisions and information-availability timestamps still need separate checks.

See the methodology (docs/METHODOLOGY.md) for the cost equation, minimum-variance objective, ranking formulas, and metric sign conventions.

Outputs and interpretation

| File | Purpose |
| report.html | Default English entry, with a Chinese language switch |
| report_zh.html | Chinese report with embedded NAV/drawdown charts, period metrics, parameters, and limitations |
| report_en.html | English report using the same computed results as the Chinese version |
| metrics.csv | Scalar performance metrics for full, development, and holdout periods |
| schedule.csv | Signal and execution dates for inspecting timing |
| target_weights.csv | Target weights at each rebalance |
| <strategy>_daily.csv | Scalar fields from each strategy's daily ledger |
| results.json | Complete structured results, including positions and trade details |
| manifest.json | Input, source, and output-file hashes plus runtime information for identifying an experiment |
| demo_prices.csv | Demo only; saves the synthetic input for reruns |

Reports and their downloadable files share an output directory. Keep that entire directory when sharing a complete report. The source repository excludes outputs/ by default. Hashes establish file identity, not data authenticity or strategy validity.

Check the data source and sample interval before comparing strategies under the same period, costs, and starting capital. CAGR and volatility use 252 trading days per year. The maximum-drawdown metric is a positive loss magnitude, while the drawdown chart uses nonpositive values. CVaR uses the worst 5% of daily losses. Development and holdout periods retain a continuous ledger; periods with fewer than two valid days do not report performance.

Structure and validation

quant_research/       Unified CLI, reporting, and stock adapter
sector_backtest/      Covariance, optimization, monthly schedule, execution, and NAV
hkquant/             Existing factor, ranking, and raw-snapshot pipeline
configs/             Reusable experiment parameters
tests/               Input, timing, formula, ledger, and regression checks
docs/                Methodology, factor definitions, validation, and roadmap
scripts/             Source packaging and original ETF archive comparison
outputs/             Local results, excluded from Git

python -m unittest discover -s tests -v

CI installs the project, runs tests, and executes both offline demos. It checks software operation; real-data reproduction, independent data verification, and statistical inference are separate levels of evidence. Core origins, third-party algorithm notices, and migration changes are documented in the provenance record (docs/CORE_PROVENANCE.md).

The earlier v0.1 migration validation passed 79 tests and checked the installed package and both demos in a clean virtual environment. The new ETF entry point was compared against the original archive across 69 rebalances, the daily ledgers of three strategies, and nine sets of performance results; the observed numerical difference was zero. This establishes migration consistency only. See the validation record (docs/VALIDATION.md) for details and reproducible commands. GitHub Actions is configured, but a remote run has not been verified.

The existing raw-stock-snapshot, SQLite-tracking, and factor-calculation entry point, main.py, remains available; instructions are archived in the legacy pipeline README (docs/LEGACY_PIPELINE.md). The legacy ETF research notes (docs/SECTOR_ETF_README.md) describe historical experiments in the original project, not the current unified interface. Migration changed some source fingerprints, so a new run cannot claim the same SHA verification identity as an old report. Historical market-data databases and research reports are not bundled in this repository.

Troubleshooting

| Symptom | Action |
| Output directory is not empty | Choose a new --output path to preserve earlier experiments |
| Ticker mismatch, duplicate rows, or missing sessions | Check the configuration and complete price panel; correct the data source without inventing observations |
| Insufficient warm-up history | Extend history to cover the initial return window, all factor windows, and consecutive ranking months |
| Fewer than N eligible stocks | Check factors, month-end volume, and consecutive months; the current implementation fails the entire run |
| Top-N violates the weight cap | Require 1 / top_n <= max_weight; three equally weighted stocks cannot satisfy the default 25% cap |
| Covariance is not positive definite | Investigate duplicate or constant prices and insufficient independent observations; the engine does not silently repair the matrix or replace the strategy |

Limits and roadmap

The fixed ETF and stock universes do not represent complete historical index membership. Stock selection can introduce selection and survivorship bias. Providers may revise adjusted histories, and saved snapshots cannot recover historical information versions that were never collected. If factor directions, parameters, or sample splits were chosen with knowledge of holdout results, subsequent reports must disclose that use and must not call the interval an unseen test set.

The current version does not include intraday data, news/forum collection, AI features, or live-trading interfaces. The completed local ETF archive comparison does not replace independent data verification. Future work needs additional data evidence and out-of-sample testing before meeting the roadmap acceptance criteria (Chinese) (docs/VERSION_ROADMAP_ZH.md).

| Version | Target decision frequency | Status |
| v0.1 | Monthly signals, daily accounting | Existing release |
| v0.11 | Research validation, eleven sector rankings, portable current-date refresh | Implemented locally |
| v1.0 | Daily | Planned |
| v2.0 | Hourly | Planned |
| v3.0 | AI and news/forum-assisted minute/second decisions | Research roadmap |

Higher-frequency versions need suitable data, timestamps, execution, and latency models. Changing the sampling parameter alone does not implement them.

Research and development team

This project was jointly developed by:

- ChungKit WAN
- LangCheng LI
- XinQuan LIU
- RunAng CAO

Licensing

A project-wide license has not yet been specified. The third-party BSD 2-Clause notice in sector_backtest/risk_models.py is retained; see the provenance record (docs/CORE_PROVENANCE.md).
