# v0.11 换电脑与一键更新

[English 主说明](PORTABLE_V011.md)。默认报告使用英文，中文可从右上角切换。总览、ETF 回测和个股回测均支持点击 ETF 代码，进入该行业配置样本的个股排名。

Windows：复制或解压整个项目文件夹，双击根目录的 **START_V011.cmd**。首次运行会在项目的 `.cache` 内下载 uv、Python 3.13.9 和所需依赖，然后下载行情、按运行时的日期重新计算并打开报告。无需预先安装 Python、Git、VS Code 或数据库服务，也无需管理员权限。

每次重新双击都会启动新的更新；月度信号使用已完成月份，报告会列出实际数据截止日。当天仍在交易中的不完整月份不会冒充已完成的月度信号。精确的数据截断规则以报告内的运行清单为准。

## 复制哪些文件

最方便的是复制完整源码包，包括 `START_V011.cmd`、`scripts`、`quant_research`、`hkquant`、`sector_backtest`、配置和 `pyproject.toml`。`.venv` 和 `.cache` 不需要复制；它们不是可迁移的安装包。启动器依据新机器与项目位置建立单独环境，避免沿用旧电脑 Python 路径。需要保留历史行情和报告时，可另行复制 `data` 和 `outputs`。

首次运行需要网络，并可能等待数分钟。Windows 支持 x64 与 ARM64。若 Windows 下载保护提示文件来自互联网，可在确认下载的是自己的源码包后查看文件属性中的解除锁定设置；组织设备的强制安全策略仍须由管理员管理。

## macOS / Linux

在项目目录执行 `sh START_V011.sh`。支持 Apple Silicon / Intel macOS 与 x64 / ARM64 的 glibc Linux；系统需有 `curl`、`tar` 和 `shasum` 或 `sha256sum`。启动器同样自动下载项目内的 Python，默认浏览器用于查看报告。当前开发环境为 Windows，macOS/Linux 脚本尚未在实机端到端验证。

## 日志和失败处理

启动日志保存于 `outputs/launcher_logs`。下载、依赖安装或计算失败会明确报错并返回失败状态，旧报告保留；启动器不会用打开旧报告来伪装本次更新成功。网络恢复后重新双击即可。若某个 uv 压缩包校验失败，删除错误提示中的该压缩包后再运行；不要忽略校验错误。

只安装运行环境、不下载行情：在 PowerShell 运行 `powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1`。安装成功时会打印项目实际使用的 Python 路径。以前的 `.venv` 不会被删除。

## 下载来源

启动器使用固定的 [Astral uv 0.9.5 官方发行包](https://github.com/astral-sh/uv/releases/tag/0.9.5)，将其 SHA-256 与代码中固定值核对后再执行；Python 由 uv 的 [托管 Python 安装机制](https://docs.astral.sh/uv/guides/install-python/) 安装，分发来自 Astral 的 `python-build-standalone`。依赖版本约束由项目 `pyproject.toml` 指定。首次运行必须能够连接 GitHub、PyPI 以及行情供应商。启动器不修改系统 PATH 或安装系统级 Python。
