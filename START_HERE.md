# Start here — Quant Research Lab v0.11

English is the primary language. [中文辅助说明](START_HERE_ZH.md) remains available.

1. Extract the complete source ZIP into a folder on your Windows computer.
2. Double-click **START_V011.cmd**. The launcher prepares Python and dependencies, downloads current prices, recalculates the reports and opens the English overview.
3. Select an ETF button, such as **XLK**, to open the stock rankings for that sector. ETF buttons also appear on the ETF and stock backtest reports. Choose any indicator and ascending or descending order. Use the language link for Chinese.

The 11 sector pages currently cover 55 configured sample stocks, five per sector. They are not the complete or historical holdings of the ETFs. All 100 indicators are shown; 65 price/volume indicators are calculated, while 35 financial indicators await point-in-time data.

Run the same launcher whenever you need fresh results. Dates come from the current clock; monthly rankings use completed months. To view the latest completed result without downloading again, open `outputs/v011/report.html`. Earlier runs remain in `outputs/v011/runs/`.

On a different Windows computer, extract the source ZIP and double-click the same launcher. Internet access is required. Python and administrator access are not required in advance. macOS/Linux launchers are supplied but have not been tested on those systems.

Read the [main README](README.md), [portable guide](docs/PORTABLE_V011.md) and [version roadmap](docs/VERSION_ROADMAP.md). Launch logs are in `outputs/launcher_logs/`.
