"""Create a source-only review bundle; no local datasets or credentials."""

from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
from quant_research import __version__


def main():
    files = [ROOT / name for name in (
        ".gitignore", "README.md", "README_EN.md", "README_ZH.md", "readme.txt", "readme_en.txt", "readme_zh.txt",
        "CHANGELOG.md", "START_HERE.md", "START_HERE_ZH.md", "pyproject.toml",
        "requirements.txt", "requirements-lock-py313-windows.txt", "config.json",
        "main.py", "rank_report.py", "setup.ps1", "START_V011.cmd", "START_V011.sh",
    )]
    for folder, suffix in (("quant_research", ".py"), ("sector_backtest", ".py"),
                           ("hkquant", ".py"), ("tests", ".py"), ("scripts", ".py"),
                           ("scripts", ".ps1"), ("scripts", ".sh"), ("quant_research", ".json"),
                           ("docs", ".md"), ("configs", ".json"), (".github/workflows", ".yml")):
        files.extend(sorted((ROOT / folder).glob("*" + suffix)))
    if not all(path.is_file() for path in files):
        raise ValueError("Missing required source file")
    content = {path.relative_to(ROOT).as_posix(): path.read_bytes() for path in files}
    manifest = {"version": __version__, "status": "local_candidate_not_published",
                "files_sha256": {name: sha256(data).hexdigest() for name, data in sorted(content.items())}}
    dest = ROOT / "outputs" / "releases" / f"Quant-research-lab-v{__version__}-source.zip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(dest, "w", compression=ZIP_DEFLATED) as archive:
        for name, data in sorted(content.items()):
            archive.writestr("Quant-research-lab/" + name, data)
        archive.writestr("Quant-research-lab/source_manifest.json", json.dumps(manifest, indent=2))
    with ZipFile(dest) as archive:
        if archive.testzip() is not None:
            raise ValueError("ZIP integrity verification failed")
        for name, data in content.items():
            if archive.read("Quant-research-lab/" + name) != data:
                raise ValueError("Source bundle read-back differs")
    digest = sha256(dest.read_bytes()).hexdigest()
    dest.with_suffix(".zip.sha256").write_text(digest + "  " + dest.name + "\n", encoding="ascii")
    print(f"Source files: {len(content)}; bundle: {dest.name}; SHA-256: {digest}")


if __name__ == "__main__":
    main()
