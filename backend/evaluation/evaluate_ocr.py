"""型番ラベル写真に対する OCR・型番推定の精度を測る評価スクリプト。

使い方（backend/ で実行）:
    python -m evaluation.evaluate_ocr --dataset evaluation/dataset
    python -m evaluation.evaluate_ocr --dataset evaluation/sample --stub   # OCR なしの動作確認

データセットは labels.csv と画像ファイルを同じフォルダに置く:
    image,model_number,maker,ocr_texts
    label_001.jpg,YH51R,TOTO,
    label_002.jpg,TCF8GM33,TOTO,TCF8GM33|TOTO|MADE IN JAPAN

ocr_texts（"|" 区切り）があれば OCR をスキップして型番抽出ロジックだけを評価する。
画像を実際に OCR する場合は空欄にする。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import statistics
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

TOP_KS = (1, 3, 5)


@dataclass
class Case:
    image: str
    model_number: str
    maker: str = ""
    ocr_texts: Optional[list[str]] = None


@dataclass
class CaseResult:
    image: str
    expected: str
    expected_maker: str
    candidates: list[str]
    detected_maker: str
    rank: Optional[int]  # 正解が何番目に出たか（1 始まり、出なければ None）
    top1_distance: int
    seconds: float
    error: str = ""


@dataclass
class Report:
    total: int = 0
    metrics: dict = field(default_factory=dict)
    results: list[CaseResult] = field(default_factory=list)


def normalize_model(value: str) -> str:
    """ハイフン・スペース等の表記ゆれを無視して比較するための正規化。"""
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def edit_distance(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, 1):
        current = [i]
        for j, char_b in enumerate(b, 1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (char_a != char_b),
                )
            )
        previous = current
    return previous[-1]


def load_cases(dataset_dir: Path) -> list[Case]:
    labels = dataset_dir / "labels.csv"
    if not labels.exists():
        raise FileNotFoundError(f"{labels} がありません")

    cases = []
    with open(labels, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            texts = (row.get("ocr_texts") or "").strip()
            cases.append(
                Case(
                    image=row["image"].strip(),
                    model_number=row["model_number"].strip(),
                    maker=(row.get("maker") or "").strip(),
                    ocr_texts=texts.split("|") if texts else None,
                )
            )
    return cases


def evaluate_case(
    case: Case,
    dataset_dir: Path,
    read_text: Callable[[str], list[str]],
    extract_candidates: Callable[[list[str]], list],
    detect_maker: Callable[[list[str]], str],
) -> CaseResult:
    started = time.perf_counter()
    texts: list[str] = []
    candidates: list[str] = []
    error = ""

    try:
        texts = case.ocr_texts if case.ocr_texts is not None else read_text(
            str(dataset_dir / case.image)
        )
        candidates = [c for c, _ in extract_candidates(texts)]
    except Exception as exc:  # 1 枚の失敗で全体を止めない
        error = f"{type(exc).__name__}: {exc}"

    seconds = time.perf_counter() - started
    expected = normalize_model(case.model_number)
    normalized = [normalize_model(c) for c in candidates]

    rank = next((i + 1 for i, c in enumerate(normalized) if c == expected), None)
    top1_distance = edit_distance(normalized[0], expected) if normalized else len(expected)

    return CaseResult(
        image=case.image,
        expected=case.model_number,
        expected_maker=case.maker,
        candidates=candidates[:5],
        detected_maker=(detect_maker(texts) or "") if texts else "",
        rank=rank,
        top1_distance=top1_distance,
        seconds=seconds,
        error=error,
    )


def summarize(results: list[CaseResult]) -> dict:
    total = len(results)
    if total == 0:
        return {}

    def hit_rate(k: int) -> float:
        return sum(1 for r in results if r.rank is not None and r.rank <= k) / total

    with_maker = [r for r in results if r.expected_maker]
    maker_ok = sum(
        1 for r in with_maker if r.detected_maker.upper() == r.expected_maker.upper()
    )
    expected_chars = sum(len(normalize_model(r.expected)) for r in results)
    times = sorted(r.seconds for r in results)

    metrics = {f"top{k}_accuracy": hit_rate(k) for k in TOP_KS}
    metrics.update(
        {
            "not_found_rate": sum(1 for r in results if r.rank is None) / total,
            "char_error_rate_top1": (
                sum(r.top1_distance for r in results) / expected_chars
                if expected_chars
                else 0.0
            ),
            "maker_accuracy": maker_ok / len(with_maker) if with_maker else None,
            "error_count": sum(1 for r in results if r.error),
            "seconds_mean": statistics.mean(times),
            "seconds_p95": times[min(total - 1, int(total * 0.95))],
        }
    )
    return metrics


def run(dataset_dir: Path, use_stubs: bool = False) -> Report:
    # 本番の DB を触らないよう、main を import する前に保存先を一時フォルダへ向ける
    root = tempfile.mkdtemp(prefix="sekou_navi_eval_")
    os.environ["SEKOU_DB_PATH"] = os.path.join(root, "eval.db")
    os.environ["SEKOU_IMAGE_DIR"] = os.path.join(root, "images")
    os.environ["SEKOU_TEMP_DIR"] = os.path.join(root, "temp_images")

    if use_stubs:
        # OCR・埋め込みモデルを読み込まない（ocr_texts 付きのデータ専用）
        from tests.stubs import install_stubs  # noqa: PLC0415

        install_stubs()

    import main  # noqa: PLC0415

    cases = load_cases(dataset_dir)
    results = [
        evaluate_case(
            case,
            dataset_dir,
            main.extract_text_from_image,
            main.extract_model_candidates,
            main.detect_maker_from_text,
        )
        for case in cases
    ]
    return Report(total=len(results), metrics=summarize(results), results=results)


def pct(value: Optional[float]) -> str:
    return "-" if value is None else f"{value * 100:.1f}%"


def render_markdown(report: Report, dataset_name: str) -> str:
    m = report.metrics
    lines = [
        f"# OCR・型番推定の精度評価（{dataset_name}）",
        "",
        f"- 評価枚数: {report.total}",
        f"- 型番 Top-1 正解率: **{pct(m.get('top1_accuracy'))}**",
        f"- 型番 Top-3 正解率: {pct(m.get('top3_accuracy'))}",
        f"- 型番 Top-5 正解率: {pct(m.get('top5_accuracy'))}",
        f"- 候補に出なかった割合: {pct(m.get('not_found_rate'))}",
        f"- Top-1 の文字誤り率: {pct(m.get('char_error_rate_top1'))}",
        f"- メーカー判定の正解率: {pct(m.get('maker_accuracy'))}",
        f"- 処理時間: 平均 {m.get('seconds_mean', 0):.2f} 秒 / p95 {m.get('seconds_p95', 0):.2f} 秒",
        f"- 例外が出た枚数: {m.get('error_count', 0)}",
        "",
        "## 外れたケース（Top-1 が不正解）",
        "",
        "| 画像 | 正解 | 推定 Top-1 | 正解の順位 |",
        "|---|---|---|---|",
    ]
    misses = [r for r in report.results if r.rank != 1]
    for r in misses:
        top1 = r.candidates[0] if r.candidates else "(なし)"
        rank = r.rank if r.rank else "圏外"
        lines.append(f"| {r.image} | {r.expected} | {top1} | {rank} |")
    if not misses:
        lines.append("| - | - | - | - |")
    return "\n".join(lines) + "\n"


def main_cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("evaluation/results"),
        help="結果の出力先フォルダ",
    )
    parser.add_argument(
        "--stub",
        action="store_true",
        help="重い AI モデルを読み込まない（ocr_texts 付きのデータで抽出ロジックだけ評価）",
    )
    args = parser.parse_args()

    report = run(args.dataset, use_stubs=args.stub)
    args.out.mkdir(parents=True, exist_ok=True)
    name = args.dataset.name

    (args.out / f"{name}.json").write_text(
        json.dumps(
            {"metrics": report.metrics, "results": [asdict(r) for r in report.results]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    markdown = render_markdown(report, name)
    (args.out / f"{name}.md").write_text(markdown, encoding="utf-8")
    print(markdown)


if __name__ == "__main__":
    main_cli()
