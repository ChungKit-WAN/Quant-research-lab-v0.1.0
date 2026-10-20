# 自己上传到 GitHub

你可以直接用浏览器上传，不需要把账号密码或登录链接交给任何人。本指南对应公开仓库 `Quant-research-lab`；它是上传说明，不代表仓库已经创建。

## 1. 解压最新源码包

使用本次更新后的 `Quant-research-lab-v0.1.0-source.zip`，右键选择“全部解压”。本地文件位于项目的 `outputs/releases/` 中。

打开解压后的 `Quant-research-lab` 文件夹，确认里面能直接看到 `README.md`、`README_EN.md`、`pyproject.toml`、`quant_research`、`docs` 等项目内容。**要上传的是这一层里面的文件和子文件夹**，不是 ZIP 本身，也不是再包一层 `Quant-research-lab` 文件夹。

这个包只包含源码、配置、文档、测试和来源校验清单；不包含 `outputs/` 运行结果、行情文件、数据库、虚拟环境或凭据。报告生成程序会输出独立的中文 `report_zh.html` 和英文 `report_en.html`，`report.html` 为语言选择入口。本地报告不随源码包上传。

## 2. 创建公开仓库

登录 GitHub，打开[新建仓库页面](https://github.com/new)，填写：

- **Owner**：你的个人账号。
- **Repository name**：`Quant-research-lab`。展示标题可以写成 `Quant Research Lab`，仓库名用连字符连接。
- **Description**：可填 `Monthly backtesting framework for sector ETF allocation and stock-factor research, with separate Chinese and English reports.`
- **Visibility**：选择 **Public**，所有人都可以查看。
- **README、.gitignore 和 License**：这一步不要自动生成。源码包已有前两项，项目整体许可证还未选择。

点击 **Create repository**。GitHub 对仓库名称和新建选项的说明见[官方创建仓库指南](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository)。

## 3. 上传解压后的内容

1. 在空仓库的页面点击 **uploading an existing file**；如果仓库已有文件，点击 **Add file → Upload files**。
2. 将解压目录**里面的全部文件和子文件夹**拖进上传区域。上传单独文件也可点击 **choose your files**。保留子目录结构。
3. 查看待上传列表，确认 `README.md` 位于根目录，路径不是 `Quant-research-lab/README.md`；同时确认包含 `.gitignore` 和 `.github/workflows/` 下的工作流文件。文件名前的点也是名称的一部分，不要删掉或改名。
4. 在提交说明中填写 `Add v0.1.0 monthly backtesting framework`。首次上传到自己的空仓库，可直接提交到默认分支，点击 **Commit changes**。如果界面要求走新分支，则按 **Propose changes** 的提示创建并合并 Pull Request。

网页上传每个文件最多 **25 MiB**，每批最多 **100 个文件**；超过批次数量可分批上传，并保持路径正确。操作与限制以 [GitHub 官方上传指南](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository)为准。

如果浏览器无法保留文件夹结构，或漏掉 `.gitignore`、`.github` 等点开头的文件／目录，改用 [GitHub Desktop](https://desktop.github.com/) 上传。可以先在 Desktop 克隆刚创建的仓库，把解压目录内的内容复制到该仓库目录，再提交并推送；官方说明见[克隆仓库](https://docs.github.com/en/desktop/adding-and-cloning-repositories/cloning-and-forking-repositories-from-github-desktop)与[提交和推送更改](https://docs.github.com/en/desktop/overview/creating-your-first-repository-using-github-desktop)。

## 4. 上传后检查

- 仓库首页直接显示本项目 README，旁边有 **Public** 标识。
- 根目录能看到 `quant_research/`、`sector_backtest/`、`hkquant/`、`tests/`、`docs/` 和 `configs/`。
- `.gitignore` 和 `.github/workflows/` 存在。打开 **Actions** 查看自动检查的实际结果；只有远程检查通过后，才可以说 GitHub CI 已通过。
- 仓库地址格式为 `https://github.com/你的账号/Quant-research-lab`，这个地址可以放到简历中。

上传源码不会自动创建版本标签或 Release。当前功能范围仍是 v0.1 月度决策；v1.0 日度、v2.0 小时和 v3.0 AI 分钟／秒级属于路线计划。
