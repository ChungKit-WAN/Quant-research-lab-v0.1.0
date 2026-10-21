# Version roadmap

[中文辅助与详细历史说明](VERSION_ROADMAP_ZH.md)

The framework combines ETF risk allocation and stock-factor selection using shared scheduling, portfolio accounting, costs and reporting. Version numbers describe implemented scope; a faster decision frequency does not establish better performance.

| Version | Decision frequency | Scope | Status |
| --- | --- | --- | --- |
| v0.1 | Monthly | ETF allocation, stock selection, next-session execution, daily accounting | Earlier version |
| v0.11 / 0.11.0 | Monthly | Research validation, all-indicator reports, 11 sector stock-ranking pages, one-click portable refresh | Implemented locally; this update is not uploaded |
| v1.0 | Daily | Daily signals, consistent execution and chronological evaluation | Planned |
| v2.0 | Hourly | Intraday data, event replay, more detailed costs and latency | Planned |
| v3.0 | Minute/second | AI-assisted event features and constrained strategy adjustments | Planned |

## v0.11

This version includes the research-validation milestone earlier discussed as v0.1.1. The Windows launcher downloads 55 configured stock samples and 11 sector ETFs using the current clock, archives raw prices and calculations, and generates English reports with Chinese companions. Clicking an ETF opens its sector sample-stock rankings. All 100 indicators are visible and sortable; 65 price/volume factors are implemented and 35 financial factors await point-in-time fundamentals.

Nine experiments are specified before execution: costs of 5/10/20 bp, a holdings-count variation, a ranking-window variation and removal of each of four factor groups' score contributions. Eligibility remains based on all 65 factors. All results and failures are retained, with continuous ledgers and matching-cost equal-weight benchmarks. The chronological holdout is not certified unseen data.

The current fixed samples and sector groupings are not historical index or ETF constituent reconstructions. Internal calendar and sample checks do not independently certify vendor prices. Financial statements and SEC filing text are not downloaded by this release.

## v1.0

Add daily signals while reusing the accounting core and clearly separating estimation windows from trading frequency. Validate missing data, market sessions, execution timing, costs and causality. Compare monthly and daily versions over consistent samples. Train, select parameters and transform features using only information available at each historical decision time.

## v2.0

Use licensed intraday observations and only closed, received bars. Model exchange time zones, daylight saving, short sessions and corrections. Replay duplicate, delayed and out-of-order events. Add spread, slippage, liquidity and volume constraints; OHLC bars alone cannot reconstruct actual fills. No provider has been selected.

## v3.0

Start with minute-level replay and paper trading before considering seconds. Preserve source events and revisions, extract structured AI features asynchronously, and pass strategy proposals through an independent risk layer. Record event publication, receipt and feature availability times. Freeze model, prompt and parameter versions and retain failures and latency. Historical evaluation must disclose possible model training-data leakage; forward paper records provide separate evidence.

Live-money trading is a separate future scope. Each release should retain reproducible commands, configurations, evidence and a matching tag once published. Describe planned features as planned and synthetic demonstrations as software checks.
