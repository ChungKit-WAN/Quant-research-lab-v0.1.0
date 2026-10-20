> 旧版入口指南：当前统一的 ETF／个股回测请先阅读 [主 README](README.md)。本文仅适用于保留的 main.py 指标流水线；目录名是示例占位。

# 美股原始数据库 → 因子计算 → 计算结果数据库

> **适用目录说明：** 本页介绍 `quant-research-lab` 中的旧版个股指标流程。
> 当前研究使用的桌面行业 ETF 工程位于 `legacy-etf-project`，请阅读 [行业 ETF 项目 README](docs/SECTOR_ETF_README.md)。
> 下文“正式项目目录”“尚未模拟持仓、现金、成交、费用”等表述只适用于本页旧版程序；不能用这里的 `main.py` 命令重放桌面 ETF 实验。

当前目标是先把真实数据保存、计算和追溯做好。运行环境为 Python，数据库选 SQLite：每个数据库是一个本地文件，不需要额外安装数据库服务器。

```text
Yahoo公开美股日线 / 自有CSV
         ↓ 获取并保留来源表快照
data/raw_market.sqlite
         ↓ 读取指定原始批次，校验SHA-256
计算65项量价指标，形成月度与连续三个月排名
         ↓ 记录原始批次、参数、代码指纹
data/calculated_market.sqlite
         ↓ 导出用于查看的结果
outputs/us_latest/report.html
```

## 现在直接运行

在 VS Code 打开本文件所在的正式项目目录：

```text
quant-research-lab
```

从 **Terminal → New Terminal** 打开终端，运行：

```powershell
.\.venv\Scripts\python.exe main.py
```

这条命令会下载配置中的美股数据，保存原始数据库，**再从原始数据库读取**，计算并保存结果数据库。程序不会直接把刚下载的内存数据绕过原始数据库送去计算。

首次换电脑或没有 `.venv` 时，执行 `setup.ps1` 安装项目环境。也可逐条运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

VS Code 若让你选择解释器，选择本项目 `.venv\Scripts\python.exe`。原先桌面的 `01.py` 练习文件不影响这个项目。

## 两个数据库分别保存什么

| 数据库 | 表 | 内容 |
|---|---|---|
| 原始库 | `ingestion_runs` | 下载批次、采集时间、来源参数、成功或失败状态、数据指纹 |
| 原始库 | `source_payloads` | 每只股票的数据源返回表快照，或导入CSV原始字节 |
| 原始库 | `daily_bars` | 同一批次的日期、代码、开高低收、复权收盘价、成交量，方便查询 |
| 结果库 | `calculation_runs` | 计算批次、原始批次ID、参数、代码和指标目录版本指纹 |
| 结果库 | `factor_definitions` | 100项候选指标的公式、方向、历史要求和实现状态 |
| 结果库 | `factor_values` | 每日每只股票的指标列：65项可计算，35项财务列留空 |
| 结果库 | `monthly_rankings` | 每月类别得分、综合排名、连续三个月平均排名及缺失原因 |

**每次采集和计算都新增批次，不覆盖旧数据。** 更新或删除已有记录会被防误改触发器拒绝。下载中途失败时，已收到的原始表及错误记录仍保存在失败批次中，计算程序不会选择失败批次。

美股配置使用 `missing_bar_policy: quarantine_empty`：只有“所有价格为空且成交量为零”的整条空记录会被单独标记。原始表完整保留；该行不进入有效日线表，其代码、日期和原因写入批次元数据的 `quality_events`。计算时在该日保留缺失观测，因此依赖该日的滚动窗口保持空值。不会用前一天价格补齐，也不会直接跳过缺口计算。部分价格损坏、价格关系错误或某只股票完全没有有效数据仍会导致本批失败。报告的“数据覆盖”会显示已识别问题。

这里的“原始数据”精确定义为：**保存数据供应商交给我们的表级数据**。`yfinance` 已经解析了 Yahoo 的响应，它不是交易所逐笔原始报文。复权数据还可能被供应商事后修订；保留采集批次可以比较日后的修订，但不能凭今天的下载恢复过去各日当时看到的所有历史版本。

## 分开执行各步骤

只采集并保存原始库：

```powershell
.\.venv\Scripts\python.exe main.py ingest
```

离线读取最近一次成功原始批次，重新计算并生成新的结果版本：

```powershell
.\.venv\Scripts\python.exe main.py calculate
```

也可指定终端打印的批次ID，保证重复研究使用同一批原始数据：

```powershell
.\.venv\Scripts\python.exe main.py calculate --raw-run raw_这里替换为真实批次ID
```

查看数据库行数与文件位置：

```powershell
.\.venv\Scripts\python.exe main.py status
```

已有真实CSV时，可导入原始库：

```powershell
.\.venv\Scripts\python.exe main.py ingest --prices your_prices.csv --start 2019-01-01 --end 2026-09-01
```

CSV字段必须是 `date,ticker,open,high,low,close,adj_close,volume`。`end` 不含该日。日期按数据所属交易所的本地交易日解释，缺价格不自动填充。来源文件原始字节会保留，计算阶段再应用日期截断。

## 默认股票与100项指标

`config.json` 暂用 AAPL、MSFT、GOOGL、AMZN、NVDA、META、JPM、JNJ、XOM、PG 十只美股跑通数据流程。**这是固定研究样本，不是标普500历史成分股，更不是完整美股市场或建议持仓。** 股票选择存在偏差，后续应取得按时点变化的历史股票池及退市数据。

指标目录见 [FACTOR_CATALOG.md](docs/FACTOR_CATALOG.md)：动量20、反转10、风险15、量价流动性20已实现；估值15、质量10、成长10等待按公告时间对齐的历史财报。35项未实现财务指标在数据库中保持 `NULL`，并记录 `awaiting_pit_fundamentals`，不会补零或用今天的财务值冒充历史值。

评分先在各类别内部平均，再应用类别权重。初始权重是待检验假设，不是最优参数。三个月排名要求连续三个月有有效数据，并按排名百分位平均；原始平均名次也保留供解释。

## 先看哪里

运行完成后打开 `outputs/us_latest/report.html`。同一目录有 `latest_rankings.csv`、`monthly_rankings.csv`、`data_coverage.csv`、`factor_registry.csv` 和 `manifest.json`。这些是方便查看的导出文件；原始及计算历史版本以两个数据库为准。导出报告会更新，数据库旧批次不覆盖。

若使用SQLite查看工具，可执行以下只读SQL：

```sql
-- 原始库：看有哪些下载批次
SELECT raw_run_id, created_at_utc, status, row_count FROM ingestion_runs;

-- 原始库：明确指定一批数据，避免把重复下载的快照混在一起
SELECT date, ticker, close, adj_close, volume
FROM daily_bars WHERE raw_run_id = '替换为真实批次ID'
ORDER BY ticker, date LIMIT 20;

-- 结果库：查看计算使用了哪一批原始数据
SELECT calculation_id, raw_run_id, code_sha256, factor_rows FROM calculation_runs;

-- 结果库：查看动量与风险指标
SELECT date, ticker, mom_return_126, risk_volatility_60
FROM factor_values WHERE calculation_id = '替换为真实计算批次ID'
ORDER BY ticker, date DESC LIMIT 20;
```

## 当前还没有完成的部分

目前完成的是数据与指标数据库，并非完整收益回测。尚未接入历史成分股、财报公告、独立美股交易日历、经核验的公司行动；尚未模拟持仓、现金、成交、费用、滑点或收益。因此没有把排名转换成声称有效的策略收益。

价格窗口计数的是已提供的日线观测，月末日期使用数据中的最后观测日；全市场同时漏日需要独立交易日历才能发现。Yahoo的Close也可能已处理拆股；`close × volume`只是成交额代理。数据的使用和再分发需遵守供应商许可。

历史港股排名入口保留在 `rank_report.py`，参数示例在 `configs/hk_example.json`。当前正式入口 `main.py` 使用美股数据库流程。

## 检查程序

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

测试数据只用于软件检查，不会被当成真实行情写进正式数据库。

来源：[yfinance](https://pypi.org/project/yfinance/)、[下载参数](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html)。
