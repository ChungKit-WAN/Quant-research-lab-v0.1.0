# 从 v0.1 更新到 v0.11：保留完整升级过程

[English 主指南](GITHUB_UPDATE_V011.md)

继续使用原仓库：[ChungKit-WAN/Quant-research-lab-v0.1.0](https://github.com/ChungKit-WAN/Quant-research-lab-v0.1.0)。在同一仓库里更新，可以保留旧提交、改动记录和两个版本的下载入口。展示名称用 **v0.11**；软件版本号用 **0.11.0**，GitHub 标签用 **v0.11.0**。

```text
保留 v0.1.0 旧版标签
        ↓
建立 codex/v0.11-upgrade 更新分支
        ↓
上传新版源码 → 创建 Pull Request → 等待自动检查通过
        ↓
合并到 main → 发布 v0.11.0 Release
```

## 第一步：先给旧版本留一个标签

2026-10-21 只读核对结果：默认分支为 `main`，旧版最新提交为 **7bf8fd05618b0835965b1b7034acb86696d660c1**，当时还没有任何版本标签。

在上传新文件之前操作：

1. 打开原仓库，进入 **Releases → Draft a new release**。若还没有 Release，界面可能显示 **Create a new release**。
2. 在 **Choose a tag** 输入 `v0.1.0`，选择创建新标签；**Target** 选择仍然是旧代码的 `main`。先核对提交短编号为 `7bf8fd0`。
3. 标题填 `v0.1.0 — Monthly research baseline`，说明可直接使用：

   `Retrospective baseline tag for the existing monthly research framework, preserved before the v0.11 upgrade. Source commit: 7bf8fd05618b0835965b1b7034acb86696d660c1.`

4. 点击 **Publish release**。这是现在补记旧版快照，不是把发布日期改到过去。

如果操作时已经存在 `v0.1.0`，核对后沿用。如果 `main` 已经改变，先找回上述旧提交再确定标签位置。**旧版标签必须指向旧代码，不能等上传新版后再给新版 main 贴 v0.1.0。** [GitHub 官方 Release 说明](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)。

## 第二步：解压这次的新源码包

解压 `Quant-research-lab-v0.11.0-source.zip`，打开里面的 `Quant-research-lab` 文件夹。这一层应直接看到：

```text
README.md / README_EN.md / README_ZH.md
START_HERE.md / START_V011.cmd / START_V011.sh
pyproject.toml / source_manifest.json
.gitignore / .github/workflows/tests.yml
quant_research/ / hkquant/ / sector_backtest/
configs/ / tests/ / scripts/ / docs/
```

上传的是这一层的全部内容。根目录应是 `README.md`，不能变成 `Quant-research-lab/README.md`。ZIP 本身留到 Release 附件步骤再传。源码包不含运行数据库、行情缓存或环境；使用者解压后双击启动器会自动下载行情并生成报告。

## 第三步：上传到一个更新分支

1. 回到原仓库的 **Code** 页面，确认在根目录和 `main` 分支。
2. 点击 **Add file → Upload files**，把解压文件夹内的文件和子目录拖进去。相同路径的源码会更新，Git 历史会保留旧内容。
3. 检查目录结构，并确认 `.gitignore`、`.github/workflows/tests.yml`、`source_manifest.json` 也在列表里。
4. 提交说明填写：`Upgrade to v0.11.0: portable refresh and ETF stock rankings`。
5. 选择 **Create a new branch for this commit and start a pull request**，分支名填 `codex/v0.11-upgrade`，再点 **Propose changes**。

本次已对照原仓库文件清单：没有需要删除的旧文件，覆盖同路径并加入新文件即可。网页每批最多 100 个文件、每个文件最多 25 MiB；本次源码包在此范围内。如果浏览器漏掉子目录或点开头的文件，可用 GitHub Desktop 克隆原仓库、创建该分支、复制覆盖源码后提交推送；保留克隆目录中的 `.git`。[官方上传步骤](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository)。

## 第四步：创建更新说明，等检查通过

Pull Request 页面设置 **base: main**、**compare: codex/v0.11-upgrade**。

- 标题：`Upgrade v0.1 to v0.11: portable refresh and ETF stock rankings`
- 描述：复制 [PULL_REQUEST_V011.md](PULL_REQUEST_V011.md) 中的英文内容。

点击 **Create pull request**。在 **Files changed** 查看新增和修改的代码；在 **Checks** 或 **Actions** 查看 `Tests and offline demos`。它会检查测试、ETF 演示、个股演示和完整离线刷新流程。

**等远程检查显示通过再点 Merge pull request，并确认合并。** 本地 109 项测试通过不等于 GitHub 已经运行通过。如果出现红色失败，打开日志，在同一个更新分支修复并重新检查。合并后再看一次新 `main` 提交的 Actions 结果。[官方 PR 步骤](https://docs.github.com/en/pull-requests/how-tos/create-pull-requests/creating-a-pull-request)。

## 第五步：发布新版 v0.11.0

合并且检查通过后，进入 **Releases → Draft a new release**：

| 字段 | 填写内容 |
| --- | --- |
| Tag | 新建 `v0.11.0` |
| Target | 已合并新版且检查通过的 `main` 提交 |
| Previous tag | 若有此字段，选择 `v0.1.0` |
| Release title | `v0.11.0 — Portable refresh and ETF stock rankings` |
| Description | 复制 [RELEASE_NOTES_V011.md](RELEASE_NOTES_V011.md) |
| Attachments | 本次源码 ZIP 和配套 `.zip.sha256` 文件 |

确认附件齐全后点击 **Publish release**。Release 与上传源码是两个步骤；仅上传文件不会自动建立新版本标签。如果又修改了源码或文档，用 `python scripts/package_source.py` 重新打包，让新包和 `source_manifest.json` 与最终上传文件一致；不要手改哈希。[官方发布步骤](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)。

## 第六步：查看“更新过程”

完成后，同一仓库就会有四种证据：

| 位置 | 可以看到什么 |
| --- | --- |
| Tags / Releases | `v0.1.0` 旧版和 `v0.11.0` 新版 |
| Pull requests → Closed | 这次升级说明、文件差异和合并记录 |
| Actions | 对应提交的自动检查结果 |
| Compare | 两版之间实际新增、修改的内容 |

两个标签建立后，可打开[版本对比 v0.1.0…v0.11.0](https://github.com/ChungKit-WAN/Quant-research-lab-v0.1.0/compare/v0.1.0...v0.11.0)。标签未建立前这个链接可能不可用。[官方版本比较说明](https://docs.github.com/en/repositories/releasing-projects-on-github/comparing-releases)。

仓库名称目前仍带 `v0.1.0`，不影响代码发布为 v0.11。先完成这次更新，以后可选改名为 `Quant-research-lab`，把版本放在标签里；改名时注意更新简历和本地远程地址。GitHub 普通仓库链接通常会自动跳转，项目网站地址需另行处理。[官方改名说明](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository)。

此次新版的 ETF 页面使用每板块 5 只配置样本股，不是完整历史成分股。英文为默认，中文为辅助；35 项财务因子仍等待历史可用数据。发布说明已保留这些边界。
