The v0.1 framework required separate setup and report commands and did not provide ETF-to-stock drill-down navigation. This update adds one-click current-date refresh and independent stock-ranking pages for all eleven sector ETFs, with English as the default and Chinese companion reports.

The reports expose all 100 candidate indicators, selectable sort directions, CSV exports, all calculated scalar portfolio metrics and per-asset weight statistics. Nine predefined research experiments retain every outcome. Source data, calculations, dates and artifact hashes remain traceable, and failed runs preserve the previous successful report.

Validation: 109 local tests passed. A live Windows launcher refresh downloaded 55 stocks and 11 ETFs, completed all nine experiments, and produced 22 sector language pages with 765 working local links and 68 verified artifact hashes. GitHub Actions runs the tests, both portfolio demos and an offline refresh; check the PR status for its remote outcome.

Scope remains monthly research using five configured sample stocks per sector. These samples do not reconstruct full historical ETF membership. The 35 financial indicators remain unavailable pending point-in-time data. Chronological holdout labels do not certify unseen data. macOS/Linux launchers have not been validated on those systems.
