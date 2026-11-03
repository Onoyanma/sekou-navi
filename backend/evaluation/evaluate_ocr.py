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
import shutil
import sqlite3
import statistics
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

TOP_KS = (1, 3, 5)
MATCH_SCORE_THRESHOLD = 50.0  # 「この商品で間違いない」と扱う照合スコアの目安


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
    # --- DB 照合（登録済み商品との突き合わせ）---
    product_rank: Optional[int] = None  # 正しい商品が照合結果の何番目か（圏外は None）
    matched_products: list[str] = field(default_factory=list)
    closed_set_score: Optional[float] = None  # 正しい商品の照合スコア
    open_set_top_score: Optional[float] = None  # 正しい商品を DB から除いたときの最高スコア


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


def rank_catalog(
    candidates: list,
    detected_maker: str,
    catalog: list[dict],
    score_product: Callable,
) -> list[tuple[float, dict]]:
    """登録済み商品を、OCR の型番候補・メーカーとの一致度が高い順に並べる。"""
    scored = []
    for product in catalog:
        score, _, _ = score_product(product, candidates, detected_maker, [])
        if score > 0:
            scored.append((score, product))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored


def evaluate_case(
    case: Case,
    dataset_dir: Path,
    read_text: Callable[[str], list[str]],
    extract_candidates: Callable[[list[str]], list],
    detect_maker: Callable[[list[str]], str],
    catalog: Optional[list[dict]] = None,
    score_product: Optional[Callable] = None,
) -> CaseResult:
    started = time.perf_counter()
    texts: list[str] = []
    scored_candidates: list = []
    candidates: list[str] = []
    error = ""

    try:
        texts = case.ocr_texts if case.ocr_texts is not None else read_text(
            str(dataset_dir / case.image)
        )
        scored_candidates = extract_candidates(texts)
        candidates = [c for c, _ in scored_candidates]
    except Exception as exc:  # 1 枚の失敗で全体を止めない
        error = f"{type(exc).__name__}: {exc}"

    seconds = time.perf_counter() - started
    expected = normalize_model(case.model_number)
    normalized = [normalize_model(c) for c in candidates]

    rank = next((i + 1 for i, c in enumerate(normalized) if c == expected), None)
    top1_distance = edit_distance(normalized[0], expected) if normalized else len(expected)

    detected_maker = (detect_maker(texts) or "") if texts else ""

    result = CaseResult(
        image=case.image,
        expected=case.model_number,
        expected_maker=case.maker,
        candidates=candidates[:5],
        detected_maker=detected_maker,
        rank=rank,
        top1_distance=top1_distance,
        seconds=seconds,
        error=error,
    )

    if catalog is not None and score_product is not None:
        ranking = rank_catalog(scored_candidates, detected_maker, catalog, score_product)
        others = [
            score for score, p in ranking if normalize_model(p["model_number"]) != expected
        ]
        true_score = next(
            (score for score, p in ranking if normalize_model(p["model_number"]) == expected),
            0.0,
        )

        result.matched_products = [p["model_number"] for _, p in ranking[:3]]
        result.closed_set_score = true_score
        # 同点の商品は、正解より上に並んだものとして数える（登録順で偶然 1 位になるのを防ぐ）
        result.product_rank = (
            1 + sum(1 for score in others if score >= true_score) if true_score > 0 else None
        )
        # 未登録の商品を撮った場合に、別の商品を自信ありげに返してしまわないか
        result.open_set_top_score = others[0] if others else 0.0

    return result


def summarize(results: list[CaseResult], threshold: float = MATCH_SCORE_THRESHOLD) -> dict:
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

    matched = [r for r in results if r.closed_set_score is not None]
    if matched:
        n = len(matched)
        metrics.update(
            {
                "product_top1_accuracy": sum(1 for r in matched if r.product_rank == 1) / n,
                "product_top3_accuracy": sum(
                    1 for r in matched if r.product_rank is not None and r.product_rank <= 3
                ) / n,
                # 登録済みの商品を撮ったとき、しきい値以上のスコアで見つけられた割合
                "product_accept_rate": sum(1 for r in matched if r.closed_set_score >= threshold) / n,
                # 未登録の商品を撮ったとき、別の商品をしきい値以上で返してしまった割合
                "false_accept_rate": sum(1 for r in matched if r.open_set_top_score >= threshold) / n,
                "match_threshold": threshold,
            }
        )
    return metrics


def read_in_temp_copy(pipeline, image_path: str) -> list[str]:
    """前処理の中間ファイルでデータセットを汚さないよう、一時フォルダのコピーを OCR する。"""
    with tempfile.TemporaryDirectory(prefix="sekou_navi_ocr_") as tmp:
        copy = os.path.join(tmp, os.path.basename(image_path))
        shutil.copyfile(image_path, copy)
        return pipeline.extract_text_from_image(copy)


def build_catalog(cases: list[Case], catalog_db: Optional[Path] = None) -> list[dict]:
    """照合用の「登録済み商品」を作る。

    写真の正解商品はすべて登録済みとし（登録済みの商品を撮り直した状況）、
    catalog_db があればそこの商品も加える。これは正解以外の紛らわしい商品（邪魔者）になり、
    DB の商品数が増えるほど照合は難しくなる。
    """
    catalog: dict[str, dict] = {}

    for case in cases:
        key = normalize_model(case.model_number)
        catalog.setdefault(
            key,
            {
                "id": len(catalog) + 1,
                "maker": case.maker,
                "model_number": case.model_number,
                "product_name": "",
                "memo": "",
                "tags": "",
            },
        )

    if catalog_db is not None:
        conn = sqlite3.connect(f"file:{catalog_db}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT maker, model_number, product_name, memo, tags FROM products"
            ).fetchall()
        finally:
            conn.close()

        for row in rows:
            key = normalize_model(row["model_number"] or "")
            if key and key not in catalog:
                catalog[key] = {"id": len(catalog) + 1, **{k: row[k] or "" for k in row.keys()}}

    return list(catalog.values())


def run(
    dataset_dir: Path,
    use_stubs: bool = False,
    catalog_db: Optional[Path] = None,
    threshold: float = MATCH_SCORE_THRESHOLD,
) -> Report:
    # 本番の DB を触らないよう、アプリの処理を import する前に保存先を一時フォルダへ向ける
    root = tempfile.mkdtemp(prefix="sekou_navi_eval_")
    os.environ["SEKOU_DB_PATH"] = os.path.join(root, "eval.db")
    os.environ["SEKOU_IMAGE_DIR"] = os.path.join(root, "images")
    os.environ["SEKOU_TEMP_DIR"] = os.path.join(root, "temp_images")

    if use_stubs:
        # OCR・埋め込みモデルを読み込まない（ocr_texts 付きのデータ専用）
        from tests.stubs import install_stubs  # noqa: PLC0415

        install_stubs()

    from evaluation.pipeline import load_pipeline  # noqa: PLC0415

    pipeline = load_pipeline()

    cases = load_cases(dataset_dir)
    catalog = build_catalog(cases, catalog_db)
    results = [
        evaluate_case(
            case,
            dataset_dir,
            lambda path: read_in_temp_copy(pipeline, path),
            pipeline.extract_model_candidates,
            pipeline.detect_maker_from_text,
            catalog=catalog,
            score_product=pipeline.score_product_from_ocr,
        )
        for case in cases
    ]
    metrics = summarize(results, threshold)
    metrics["catalog_size"] = len(catalog)
    return Report(total=len(results), metrics=metrics, results=results)


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
    ]
    if "product_top1_accuracy" in m:
        lines += [
            f"## DB 照合込み（登録済み商品 {m['catalog_size']} 件、合格スコア {m['match_threshold']:.0f} 以上）",
            "",
            f"- 商品 Top-1 正解率: **{pct(m['product_top1_accuracy'])}**",
            f"- 商品 Top-3 正解率: {pct(m['product_top3_accuracy'])}",
            f"- 登録済み商品を自信を持って見つけられた割合: {pct(m['product_accept_rate'])}",
            f"- 未登録の商品を別の商品と取り違えた割合（誤受理）: {pct(m['false_accept_rate'])}",
            "",
        ]
    lines += [
        "## 外れたケース（Top-1 が不正解）",
        "",
        "| 画像 | 正解 | 推定 Top-1 | 正解の順位 | DB 照合での順位 |",
        "|---|---|---|---|---|",
    ]
    misses = [r for r in report.results if r.rank != 1]
    for r in misses:
        top1 = r.candidates[0] if r.candidates else "(なし)"
        rank = r.rank if r.rank else "圏外"
        product_rank = r.product_rank if r.product_rank else "圏外"
        lines.append(f"| {r.image} | {r.expected} | {top1} | {rank} | {product_rank} |")
    if not misses:
        lines.append("| - | - | - | - | - |")
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
    parser.add_argument(
        "--catalog-db",
        type=Path,
        help="照合の邪魔者として加える登録済み商品の SQLite（products テーブル）",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=MATCH_SCORE_THRESHOLD,
        help="照合スコアがこの値以上なら「見つかった」とみなす",
    )
    args = parser.parse_args()

    report = run(
        args.dataset,
        use_stubs=args.stub,
        catalog_db=args.catalog_db,
        threshold=args.threshold,
    )
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
