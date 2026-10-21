# Update v0.1 to v0.11 on GitHub

English is primary. [中文操作指南](GITHUB_UPDATE_V011_ZH.md).

Use the existing repository: [ChungKit-WAN/Quant-research-lab-v0.1.0](https://github.com/ChungKit-WAN/Quant-research-lab-v0.1.0). Keep its history and publish the upgrade through a branch, pull request and release. The visible version is **v0.11**; the package and release tag use **0.11.0** and **v0.11.0**.

```text
main at v0.1 → tag v0.1.0
             → codex/v0.11-upgrade → pull request → checks → merge
                                                        → tag/release v0.11.0
```

## 1. Preserve the old version first

Read-only inspection on 2026-10-21 found `main` at **7bf8fd05618b0835965b1b7034acb86696d660c1**, with no remote tags. Confirm that the old source still matches this commit before proceeding.

Before uploading the new source, open **Releases → Draft a new release**. Create tag **v0.1.0** targeting the current old `main`, title it **v0.1.0 — Monthly research baseline**, and publish it with this description:

> Retrospective baseline tag for the existing monthly research framework, preserved before the v0.11 upgrade. Source commit: 7bf8fd05618b0835965b1b7034acb86696d660c1.

If the tag already exists when you follow this guide, verify and reuse it. Do not move it to the new code. If `main` has changed, identify the old commit before tagging. This is a baseline snapshot recorded now, not a backdated release.

## 2. Upload the extracted source to an upgrade branch

Extract **Quant-research-lab-v0.11.0-source.zip**. Open its `Quant-research-lab` folder: `README.md`, `pyproject.toml`, `START_V011.cmd`, `.github`, packages, tests and docs should be directly inside.

From the existing repository root on `main`, choose **Add file → Upload files**. Drag the contents of that folder into the upload area, preserving paths. Include `.gitignore`, `.github/workflows/tests.yml` and `source_manifest.json`. Upload the source files here; attach the ZIP later as a release asset. Avoid a nested `Quant-research-lab/README.md` path.

Use commit message **Upgrade to v0.11.0: portable refresh and ETF stock rankings**. Choose a new branch named **codex/v0.11-upgrade** and propose the changes. The audited old tree has no tracked files missing from this source bundle, so this update requires no old-file deletion.

The browser supports at most 100 files per batch and 25 MiB per file. If it loses folder paths or dot-prefixed entries, clone the same repository with GitHub Desktop, create the upgrade branch, copy the extracted contents over matching files, review, commit and push. Preserve the clone's `.git` folder. [Upload documentation](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository).

## 3. Review the upgrade and run checks

Open a pull request from **codex/v0.11-upgrade** into **main**, titled **Upgrade v0.1 to v0.11: portable refresh and ETF stock rankings**. Paste the text from [PULL_REQUEST_V011.md](PULL_REQUEST_V011.md) into its description.

Use **Files changed** to review the upgrade. Confirm English documentation, all 11 sector pages in the generator, the launcher and updated tests/workflow are included. Wait for **Tests and offline demos** to pass before merging. The workflow runs unit/integration tests, both portfolio demos and the complete offline refresh. Local success does not establish remote CI success. If a check fails, inspect its log and fix the same branch before merging. [Pull request documentation](https://docs.github.com/en/pull-requests/how-tos/create-pull-requests/creating-a-pull-request).

After merging, check the workflow for the new `main` commit too. Keep the merged pull request as the visible change record.

## 4. Publish v0.11.0

Open **Releases → Draft a new release**. Create tag **v0.11.0** on the tested merged `main` commit. Select **v0.1.0** as the previous tag when available. Title: **v0.11.0 — Portable refresh and ETF stock rankings**. Paste [RELEASE_NOTES_V011.md](RELEASE_NOTES_V011.md), attach the supplied source ZIP and `.zip.sha256` file, and publish. [Release documentation](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).

If you edit source files after receiving the bundle, rebuild it with `python scripts/package_source.py` so its manifest and release asset match the uploaded revision. Do not manually alter recorded hashes.

## 5. Show the update history

The old tag preserves the baseline, the pull request explains the changes, Actions records checks, and the new release provides the download. Once both tags exist, use [v0.1.0…v0.11.0](https://github.com/ChungKit-WAN/Quant-research-lab-v0.1.0/compare/v0.1.0...v0.11.0) to inspect the diff. This comparison link becomes usable after publishing the tags. [Comparing releases](https://docs.github.com/en/repositories/releasing-projects-on-github/comparing-releases).

The repository's existing name can remain during this upgrade. A later optional rename to `Quant-research-lab` keeps version numbers in tags rather than the project name. GitHub redirects ordinary repository links after a rename; project-site URLs need separate handling. [Renaming documentation](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository).

The source ZIP contains no generated market data, databases or environments. After downloading and extracting it, users double-click `START_V011.cmd` to generate current-date reports. Each ETF page currently covers five configured stock samples, not complete historical fund holdings.
