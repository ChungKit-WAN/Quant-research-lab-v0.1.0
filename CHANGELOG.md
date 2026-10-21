# Changelog

English is primary. [Chinese supplementary history](docs/CHANGELOG_ZH.md).

## 0.11.0 — 2026-10-21

- Add current-date `refresh`: download prices, archive raw and calculated databases, validate exchange sessions and generate ETF, stock and research-validation reports.
- Show all 100 indicators, including 65 calculated price/volume factors and 35 financial factors awaiting point-in-time data. Support ascending/descending rankings and CSV exports across 11 sector pages and 55 configured stock samples.
- Make English the default report and documentation language, retaining Chinese companion pages. The overview and both backtest reports provide clickable ETF buttons leading to sector sample-stock rankings; ETF ticker cells in weight tables also link to these pages.
- Preserve nine predefined cost, holdings-count, ranking-window and factor-group contribution experiments, including failures. Display all calculated scalar performance metrics and per-asset actual weight statistics.
- Add a Windows launcher with verified downloads and a project-local Python environment keyed to machine and location. Preserve TLS verification and support non-ASCII directories. macOS/Linux scripts remain untested on those platforms.
- Use completed New York sessions and true exchange-calendar month ends. Failed runs never replace the latest successful report. Retain source, configuration, experiment-plan and artifact hashes.

This uses the requested v0.11 name and incorporates the research-validation scope previously discussed as v0.1.1. This update has not been uploaded to GitHub. Point-in-time financial factors, complete historical membership and independent market-data certification remain future work.

## 0.1.0 — earlier monthly framework

- Combine ETF risk allocation and stock-factor selection under the `quant_research` CLI, using shared monthly signals, next-session execution and daily accounting with transaction costs.
- Add three ETF allocation methods and stock selection using the existing 65 price/volume factors, deterministic synthetic demos, packaging metadata and CI configuration.
- Generate separate English/Chinese reports from the same results, with documentation for methods, timing, parameters and reproducibility.
- Preserve the legacy stock pipeline and ETF core provenance. Describe daily, hourly and AI event-driven versions as future scope.

Synthetic results validate software operation and are not evidence of market performance. Historical reports and source fingerprints are preserved separately.
