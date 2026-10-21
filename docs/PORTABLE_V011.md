# Portable setup and current-date refresh

[中文辅助](PORTABLE_V011_ZH.md)

On Windows, extract the entire source bundle and double-click **START_V011.cmd**. The launcher verifies the downloaded runtime tool, installs Python 3.13.9 and project dependencies under `.cache`, downloads prices, calculates results and opens the English report. The report includes a Chinese language switch and clickable ETF buttons leading to sector stock rankings.

No preinstalled Python, Git, editor or database service is required. The launcher does not modify system PATH or require administrator access. First use needs internet access to GitHub, Python package sources and Yahoo Finance. It may take several minutes.

## Moving to another computer

Copy the source ZIP and extract it into a new folder. Keep the complete project, including the launchers, `scripts`, Python packages, configuration and `pyproject.toml`. Do not depend on a copied `.venv` or `.cache`: the launcher creates an environment keyed to the computer and project location. Copy `data` and `outputs` separately if historical runs are needed; they are excluded from the source ZIP.

The Windows launcher supports x64 and ARM64; end-to-end validation has been performed on the current Windows machine with a fresh environment and relocated project. A second physical computer and ARM64 hardware have not been tested.

## Dates, output and navigation

Each launch resolves the current date again. The default window includes five research years, three earlier warmup years and a trailing 24-month chronological holdout. Prices stop at a completed New York session with a two-hour vendor buffer. Signals use fully completed exchange-calendar months. Shanghai reaching a new month does not mean New York's month-end session has closed.

`outputs/v011/report.html` opens the latest fully successful report in English. Use an ETF button, such as XLK, on the overview or either backtest report to enter its sector stock rankings. Each page shows the configured stock sample, not complete or historical ETF holdings. Chinese companion pages preserve the same data and navigation.

All runs are stored separately under `outputs/v011/runs/`. A download or calculation failure retains its evidence and leaves the previous successful report in place. Logs are in `outputs/launcher_logs/`. Fix the reported cause and rerun; failed downloads never become synthetic data silently.

## Other operating systems and setup only

On macOS/Linux, run `bash START_V011.sh` from the project folder. The script targets Apple Silicon/Intel macOS and x64/ARM64 glibc Linux and needs `curl`, `tar`, and `shasum` or `sha256sum`. These platforms have not been validated end to end.

For setup without a market-data refresh, run `powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1`. It prints the installed interpreter path. Existing environments are preserved.

The launcher uses the pinned [official Astral uv 0.9.5 release](https://github.com/astral-sh/uv/releases/tag/0.9.5) with a fixed SHA-256 checksum. Python is installed through uv's managed Python mechanism. Dependencies are defined in `pyproject.toml`. TLS verification remains enabled.
