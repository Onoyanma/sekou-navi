"""時間計測の実験（docs/experiment/README.md）の記録を集計する。

使い方（backend/ で実行）:
    python -m evaluation.analyze_time_experiment ../docs/experiment/record_sheet.csv

人数が少ないので検定はせず、方法ごとの中央値・平均・幅・成功率を並べる。
失敗（時間切れ）の秒数は制限時間（180 秒）として数える。
"""

from __future__ import annotations

import argparse
import csv
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

TIME_LIMIT_SECONDS = 180.0


@dataclass
class Row:
    participant: str
    item: str
    method: str  # A（従来）/ B（施工ナビ）
    registered: str  # 方法 B のとき yes / no
    seconds: float
    success: bool
    notes: str = ""


def load_rows(path: Path) -> list[Row]:
    rows = []
    with open(path, encoding="utf-8", newline="") as f:
        for line_no, record in enumerate(csv.DictReader(f), start=2):
            method = (record.get("method") or "").strip().upper()
            if method not in ("A", "B"):
                raise ValueError(f"{line_no} 行目: method は A か B にしてください: {method!r}")

            seconds = float(record["seconds"])
            success = (record.get("success") or "").strip() == "1"
            rows.append(
                Row(
                    participant=(record.get("participant") or "").strip(),
                    item=(record.get("item") or "").strip(),
                    method=method,
                    registered=(record.get("registered") or "").strip().lower(),
                    # 失敗は、実際にかかった秒数ではなく制限時間として数える
                    seconds=seconds if success else TIME_LIMIT_SECONDS,
                    success=success,
                    notes=(record.get("notes") or "").strip(),
                )
            )
    return rows


def describe(rows: list[Row]) -> Optional[dict]:
    if not rows:
        return None

    seconds = [r.seconds for r in rows]
    return {
        "n": len(rows),
        "median": statistics.median(seconds),
        "mean": statistics.mean(seconds),
        "min": min(seconds),
        "max": max(seconds),
        "success_rate": sum(1 for r in rows if r.success) / len(rows),
    }


def summarize(rows: list[Row]) -> dict:
    a = [r for r in rows if r.method == "A"]
    b = [r for r in rows if r.method == "B"]

    summary = {
        "A": describe(a),
        "B": describe(b),
        "B_registered": describe([r for r in b if r.registered == "yes"]),
        "B_unregistered": describe([r for r in b if r.registered == "no"]),
        "participants": sorted({r.participant for r in rows}),
    }

    if summary["A"] and summary["B"]:
        summary["median_reduction"] = 1 - summary["B"]["median"] / summary["A"]["median"]

    return summary


def format_stats(label: str, stats: Optional[dict]) -> str:
    if not stats:
        return f"| {label} | 0 | - | - | - | - |"

    return (
        f"| {label} | {stats['n']} | {stats['median']:.0f} 秒 | {stats['mean']:.0f} 秒 "
        f"| {stats['min']:.0f}〜{stats['max']:.0f} 秒 | {stats['success_rate'] * 100:.0f}% |"
    )


def render_markdown(summary: dict) -> str:
    lines = [
        "# 時間計測の結果",
        "",
        f"- 参加者: {len(summary['participants'])} 人（{', '.join(summary['participants'])}）",
        f"- 失敗（時間切れ）は {TIME_LIMIT_SECONDS:.0f} 秒として集計",
        "",
        "| 方法 | 回数 | 中央値 | 平均 | 幅 | 成功率 |",
        "|---|---|---|---|---|---|",
        format_stats("A: 従来のやり方", summary["A"]),
        format_stats("B: 施工ナビ", summary["B"]),
        format_stats("　B のうち登録済み", summary["B_registered"]),
        format_stats("　B のうち未登録", summary["B_unregistered"]),
        "",
    ]

    if "median_reduction" in summary:
        lines.append(
            f"- 中央値の変化: 従来より **{summary['median_reduction'] * 100:.0f}%** "
            + ("短縮" if summary["median_reduction"] >= 0 else "（長くなった）")
        )

    lines.append("- 参加者が少ないため、検定は行っていない。結果は傾向として扱う。")
    return "\n".join(lines) + "\n"


def main_cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("csv", type=Path)
    args = parser.parse_args()

    print(render_markdown(summarize(load_rows(args.csv))))


if __name__ == "__main__":
    main_cli()
