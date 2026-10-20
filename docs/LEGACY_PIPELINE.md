> 历史说明：本文保留旧版流水线的功能与限制，目录用通用名称替代。当前统一框架见 [主 README](../README.md)。原始文档另存于本机 outputs/local_document_archive，不随仓库发布。

# Equity Research Data Pipeline

> **目录与进度说明：本文件以下原有内容描述 Documents 目录中的旧版个股指标流水线。**
> 当前会话的 11 只行业 ETF 风险配置工程实际位于 `legacy-etf-project`，两份目录的代码与数据不同。
> ETF 工程的计算主链、基线报告和本次分红敏感性实验已完成；其运行方法、模块职责与待补证据见 **[行业 ETF 项目 README](SECTOR_ETF_README.md)**。
> 下文的 `main.py`、`data/raw_market.sqlite` 和“尚未计算交易收益”等说明仅适用于本目录旧版程序，不代表桌面 ETF 工程的当前进度。
>
> `docs/SECTOR_ETF_README.md` 同时可作为桌面项目的 `README.md` 使用。当前工作区未复制或迁移桌面项目代码及数据。

**Public US stock data → append-only raw SQLite database → read a specific raw snapshot → calculate indicators → separate versioned result database.**

See [the Chinese operating guide](../START_HERE_ZH.md) and [100-candidate indicator catalogue](FACTOR_CATALOG.md).

## Quick start

Python 3.11+; prepared and tested with Python 3.13. In Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Default configuration uses ten selected US stocks and daily data from 2019. This is a workflow sample, **not a historical S&P 500 universe**. It has unresolved selection and survivorship bias.

Open `outputs/us_latest/report.html`. Commands can also be run independently:

```powershell
.\.venv\Scripts\python.exe main.py ingest
.\.venv\Scripts\python.exe main.py calculate --raw-run raw_REPLACE_WITH_BATCH_ID
.\.venv\Scripts\python.exe main.py status
```

`calculate` performs no market download. Without `--raw-run` it explicitly selects the latest successful ingestion; failed batches are excluded. Each ingestion and calculation adds a new version. Report exports update while database history is retained.

## Storage and lineage

| File | Tables |
|---|---|
| `data/raw_market.sqlite` | `ingestion_runs`, `source_payloads`, `daily_bars` |
| `data/calculated_market.sqlite` | `calculation_runs`, `factor_definitions`, `factor_values`, `monthly_rankings` |

Raw storage preserves provider table snapshots or original imported CSV bytes alongside a queryable daily-bar view. SHA-256 checks validate both payload and bar integrity before calculation. Append-only triggers protect prior records against accidental update/deletion. Each write is transactional. Failed downloads retain available original tables and an error, without becoming eligible inputs.

US configuration explicitly uses `missing_bar_policy: quarantine_empty`: a provider row with all five prices missing and zero volume is preserved in the original payload and recorded in `ingestion_runs.metadata_json.quality_events`, but excluded from valid `daily_bars`. Calculation restores a missing observation at that date, so affected rolling windows stay unavailable instead of jumping across the gap. Partial corruption, invalid OHLC, and a wholly unusable ticker still fail the batch. The default downloader policy remains `reject` unless explicitly configured.

Derived rows refer to a calculation batch, which refers to the source batch and database, parameter JSON, source metadata, code hash and indicator-definition hash. Query with an explicit `raw_run_id` / `calculation_id` to avoid mixing repeat snapshots. SQLite files should be backed up after closing active connections; this is local research storage, not a multi-user warehouse.

## Computation

100 candidates are defined: momentum 20, reversal 10, risk 15 and liquidity 20 are implemented; value 15, quality 10 and growth 10 await point-in-time fundamentals. The latter remain SQL NULL with explicit status rather than zeros. Missing history also remains NULL. Direction signs and weights are hypotheses, not evidence of predictive power.

Monthly scores average direction-adjusted percentile scores inside each group, then combine groups with explicit weights. All 65 implemented indicators must be available. Missing/zero-volume anchor quotes cannot inherit previous quotes. Trailing rankings require three consecutive valid calendar months. The current `as_of` calendar month is excluded. Rank percentiles are averaged; ordinary mean ranks are retained for interpretation.

The current release intentionally does not calculate trading returns, Sharpe ratios or a portfolio equity curve. Historical membership, corporate actions, an independent trading calendar, point-in-time financial data, execution, cash, fees and risk constraints remain subsequent research work.

## Source and reproducibility limits

`yfinance` is a third-party Yahoo Finance downloader. Preserved "raw" means its returned table, not exchange-original data or raw HTTP packets. Yahoo can revise history and adjustment factors. Acquisition snapshots preserve future revisions for comparison but cannot reconstruct historical information vintages that were never acquired. Close may be split-adjusted; `close*volume` is only an approximate turnover proxy.

Windows count supplied observations, not an independently audited US exchange calendar. Monthly anchors use the last observed date. Public data may omit delisted securities; data licenses and provider access terms still apply. Market data and local databases are excluded from Git.

Import your own CSV with `main.py ingest --prices prices.csv --start YYYY-MM-DD --end YYYY-MM-DD`. Schema: `date,ticker,open,high,low,close,adj_close,volume`; end is exclusive. Original CSV bytes are kept; validated bars are subsequently filtered by the calculation cutoff. Missing adjusted closes and invalid OHLC are rejected.

The previous Hong Kong ranking entry point remains `rank_report.py` with `configs/hk_example.json`. Shared price-based calculations are in `hkquant/`; the current `main.py` entry point uses US dates and storage.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests cover input validation, causal prefix invariance, known formulas, warm-up periods, missing months, group weights, membership intervals, byte preservation, append-only behavior, failed batches, atomic rollback, integrity checks and calculation lineage. Artificial fixtures are used only in tests.
