# v0.11.0 — Portable refresh and ETF stock rankings

This release extends the monthly ETF and stock research framework with current-date refresh, research-validation experiments and interactive sector reports.

## Added and improved

- One-click Windows setup and refresh: prepare a project-local Python environment, download prices, archive raw and calculated data, and generate reports using the current clock.
- Eleven independent ETF-sector stock-ranking pages. Click an ETF from the overview or either portfolio report to view its sector stock sample.
- All 100 indicator definitions, formulas and statuses, with selectable ascending/descending rankings and CSV exports. Missing values remain unranked and sort last.
- English default reports and documentation, with Chinese companion pages.
- All calculated scalar performance metrics and per-asset actual weight statistics in the portfolio reports.
- Nine predefined research experiments covering transaction costs, holdings count, ranking window and factor-group contribution removal. Save all results and failures.
- Completed-session and month-end checks, source/artifact hashes and preserved run history. Failed refreshes leave the previous successful report available.

## Validation evidence

- 109 local unit and integration tests passed on Windows.
- The Windows launcher completed a live refresh for 55 stocks and 11 ETFs. All nine validation experiments completed.
- The final English-report run contained 22 sector language pages; 765 local links and 68 artifact hashes were checked.
- GitHub Actions is configured for tests and offline demonstrations. Consult the checks on the tagged commit for the actual remote result.

## Scope and limitations

Decisions remain monthly. Each sector currently contains five configured stock samples; these are not complete or historical ETF constituents. Of 100 candidate indicators, 65 price/volume factors are implemented and 35 financial factors await point-in-time fundamentals. The workflow downloads prices and generates reports; it does not download company annual-report or SEC filing text.

A chronological holdout does not certify unseen data. Fixed-universe selection bias and vendor adjustment revisions remain. Internal data checks do not constitute independent price certification. macOS/Linux launcher scripts are supplied but have not been tested on those systems.

## Getting started

Download and extract `Quant-research-lab-v0.11.0-source.zip`, then double-click `START_V011.cmd` on Windows. Internet access is required. Open `START_HERE.md` for instructions. The source bundle excludes generated reports, market data, databases and runtime caches; the launcher builds these locally.

The product name **v0.11** corresponds to package **0.11.0** and release tag **v0.11.0**. This release includes the earlier research-validation milestone discussed as v0.1.1. Daily, hourly and AI event-driven versions remain planned.

中文辅助：本版增加当前日期一键更新、11 个 ETF 板块独立个股排名页、全部指标升降序查看和研究验证报告。默认英文，可切换中文；每板块当前为 5 只样本股，35 项财务指标仍待数据。
