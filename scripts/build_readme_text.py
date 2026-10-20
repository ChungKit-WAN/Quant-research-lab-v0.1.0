"""Build readable plain-text editions of the Chinese and English READMEs."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]

DIAGRAMS = {
    "zh": (
        """统一框架流程：
1. CSV 行情或合成演示
2. 校验字段、标的及交易日
3. 生成月末信号与下一交易日执行计划
4. 分别生成目标权重：
   - ETF：收益窗口与协方差估计 → 等权及两种最小方差配置
   - 个股：65 因子与连续月排名 → 全池等权及 Top-N 等权
5. 汇入统一目标权重接口
6. 共用持仓、现金及费用账本
7. 计算日度净值与分期指标
8. 输出独立中文／英文报告、CSV、JSON 及哈希清单""",
        """信号与记账时序：
1. t 月末收盘：仅使用截至 t 的历史数据，计算目标权重。
2. 执行收盘前：旧持仓承担此段收益。
3. 下一交易日收盘：调仓并支付交易费用。
4. 执行收盘之后：新持仓开始获得收益。
5. 后续交易日：逐日估值，直到下一次调仓。""",
    ),
    "en": (
        """Shared workflow:
1. Price CSV or synthetic demo
2. Validate fields, universe, and sessions
3. Build month-end signals and the next-session execution schedule
4. Generate target weights in two branches:
   - ETFs: return window and covariance estimates → equal weight and two minimum-variance methods
   - Stocks: 65 factors and consecutive monthly rankings → universe equal weight and Top-N
5. Feed both branches into the common target-weight interface
6. Apply the shared positions, cash, and cost ledger
7. Compute daily NAV and period metrics
8. Export separate Chinese/English reports, CSV, JSON, and the hash manifest""",
        """Signal and execution timing:
1. Month-end close t: use historical information through t to set target weights.
2. Before the execution close: old holdings earn the pre-trade returns.
3. At the next session's close: rebalance and pay transaction costs.
4. After the execution close: new holdings begin to earn returns.
5. On subsequent sessions: mark positions to market until the next rebalance.""",
    ),
}


def to_plain_text(markdown: str, language: str) -> str:
    diagrams = iter(DIAGRAMS[language])
    count = 0

    def replace_diagram(match: re.Match) -> str:
        nonlocal count
        count += 1
        return next(diagrams)

    text = re.sub(r"```mermaid\r?\n.*?```", replace_diagram, markdown, flags=re.S)
    if count != len(DIAGRAMS[language]):
        raise ValueError(f"Expected two {language} diagrams; found {count}")
    text = re.sub(r"^```[^\n]*\n?", "", text, flags=re.M)
    text = re.sub(r"^#{1,6} ", "", text, flags=re.M)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    text = text.replace("**", "").replace("`", "")
    text = re.sub(r"^\|(?:\s*:?-+:?\s*\|)+\s*\n", "", text, flags=re.M)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.rstrip() + "\n"


def main() -> None:
    for language, source, target in (
        ("zh", "README.md", "readme.txt"),
        ("en", "README_EN.md", "readme_en.txt"),
    ):
        text = to_plain_text((ROOT / source).read_text(encoding="utf-8"), language)
        (ROOT / target).write_text(text, encoding="utf-8")
        print(f"{source} -> {target}")


if __name__ == "__main__":
    main()
