# Core calculation provenance

Imported on 2026-10-19 from the existing desktop research directory named `量化回测模型`. The source project implements fixed-sector ETF risk allocation. Only the five Python calculation modules listed below were copied; the source directory was read only. No database, downloaded market data, historical report, credentials, or other private storage was copied.

The destination is `sector_backtest/` in this repository. File hashes below are SHA-256 hashes of the exact file bytes at migration time, not canonical JSON report hashes.

| File | Original file SHA-256 | Imported file SHA-256 |
| --- | --- | --- |
| `risk_models.py` | `7e05347b764597672ac48de5c038940eacb05a348bb4f0fe2b678369ccd58672` | `7e05347b764597672ac48de5c038940eacb05a348bb4f0fe2b678369ccd58672` |
| `portfolio.py` | `52266693c3d16aa12767d693ea02f27c882c09df3d6f5e20cd8c68d4c8c3b50a` | `52266693c3d16aa12767d693ea02f27c882c09df3d6f5e20cd8c68d4c8c3b50a` |
| `execution.py` | `238c81d56cbc350a3b906f2391d46ea51e73518a88cf6a9a6a52ad75aae3a7af` | `238c81d56cbc350a3b906f2391d46ea51e73518a88cf6a9a6a52ad75aae3a7af` |
| `backtest.py` | `561e7fda93051d890f5993d86e7072d7e97e2d3060d13404f5d9af5b13014211` | `f9e6e635b7164f29705982b7c8a87b42c925d9a1ba5b95dcbc55e59d068a89fb` |
| `performance.py` | `00b735cc919a4bb8347f646e1ce277b395df00186d583429d635879f381cc46b` | `00b735cc919a4bb8347f646e1ce277b395df00186d583429d635879f381cc46b` |

## Import adaptation

Only `backtest.py` was changed: `from execution import rebalance_synthetic_portfolio` became `from .execution import rebalance_synthetic_portfolio` so the copied code imports its execution module within the new package. The other four modules are byte-for-byte copies. Algorithms, formulas, input validation, accounting conventions, diagnostics, and numerical tolerances were retained.

The Ledoit–Wolf constant-correlation covariance implementation in `risk_models.py` retains the original attribution and full BSD 2-clause notice for Olivier Ledoit and Michael Wolf. Its source reference is preserved in the module. These provenance notes do not replace that notice.

## Relationship to archived research reports

The original research pipeline embeds source-code fingerprints, package versions, exact calculated values, and absolute paths in pinned JSON reports. The package import adaptation changes the `backtest.py` implementation fingerprint. A new run also uses new input and artifact identities. Do not present new package outputs as a replay of the original archived reports, replace an old expected hash merely to force a pass, or reuse old report pins with the migrated package.

The original desktop files and their archived results remain the historical source. Fresh package runs must record their own configuration, inputs, dependencies, code fingerprints, and outputs. Publishing this code does not certify historical data availability or independently validate adjusted prices and corporate actions.

## Migration verification

The five original modules passed a synthetic-data smoke check of 215 ledger sessions and four rebalances, including entry-cost funding and continuous NAV, and the minimum-variance solver matched the analytic solution for a diagonal covariance matrix. The imported modules were checked for byte preservation (except the single documented import) and syntax. This check uses generated data and is not a market-performance result.
