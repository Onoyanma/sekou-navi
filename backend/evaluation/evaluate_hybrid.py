"""OCR（テキスト）と画像検索（CLIP）を併用すると、どこまで商品を見つけられるかを測る。

実際の /similar-search と同じ統合ロジック（merge_similar_search_results）を使い、
同じ写真で次の 3 通りを比べる。

    text   : OCR の型番・メーカーだけ（DB 照合）
    image  : CLIP の画像類似だけ
    hybrid : 両方を統合（アプリの実際の挙動）

評価は「1 枚ずつ除外（leave-one-out）」で行う。ある写真を問い合わせ画像にしたとき、
登録済みの画像は「その写真以外のすべて」とする。同じ商品を撮った別の写真が
登録されていれば画像検索で見つかるはず、という状況を再現している。

使い方（backend/ で実行）:
    python -m evaluation.evaluate_hybrid --dataset evaluation/dataset --catalog-db ../products.db
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from evaluation.evaluate_ocr import (
    Case,
    build_catalog,
    load_cases,
    normalize_model,
    pct,
)

MODES = ("text", "image", "hybrid")
LABEL_IMAGE_TYPE = "型番ラベル"  # 評価写真はすべて型番ラベルの写真


@dataclass
class QueryResult:
    image: str
    expected: str
    ranks: dict  # モード名 -> 正しい商品の順位（見つからなければ None）
    has_registered_image: bool  # 同じ商品の別の写真が登録済みか


def pessimistic_rank(expected: str, scored: list[tuple[float, str]]) -> Optional[int]:
    """expected の順位。同点は正解より上として数える。スコア 0 以下は見つかっていない扱い。"""
    target = normalize_model(expected)
    true_score = next((s for s, m in scored if normalize_model(m) == target), None)
    if true_score is None or true_score <= 0:
        return None
    others = [s for s, m in scored if normalize_model(m) != target]
    return 1 + sum(1 for s in others if s >= true_score)


def image_only_ranking(
    query_embedding: np.ndarray,
    registered: list[tuple[str, np.ndarray]],
    min_similarity: float,
) -> list[tuple[float, str]]:
    """商品ごとに最も似ている登録画像の類似度を取り、高い順に並べる。"""
    best: dict[str, float] = {}
    for model, embedding in registered:
        similarity = float(np.dot(query_embedding, embedding))
        if similarity >= min_similarity and similarity > best.get(model, -1.0):
            best[model] = similarity
    return sorted(((s, m) for m, s in best.items()), reverse=True)


def evaluate_queries(
    cases: list[Case],
    features: dict,
    catalog: list[dict],
    main,
    min_similarity: Optional[float] = None,
) -> list[QueryResult]:
    min_similarity = main.MIN_SIMILARITY if min_similarity is None else min_similarity
    product_by_model = {normalize_model(p["model_number"]): p for p in catalog}
    results = []

    for query in cases:
        feature = features[query.image]
        registered = [
            (normalize_model(c.model_number), features[c.image]["embedding"])
            for c in cases
            if c.image != query.image
        ]

        texts = feature["texts"]
        candidates = main.extract_model_candidates(texts)
        maker = main.detect_maker_from_text(texts)
        hints = main.extract_product_name_hints(texts)
        similar_models = main.find_similar_model_numbers(candidates, catalog)

        # アプリと同じ形式の画像検索結果（商品ごとに最良の 1 枚）
        image_ranking = image_only_ranking(
            feature["embedding"], registered, min_similarity
        )
        image_results = [
            {
                "product": main.product_row_to_result(product_by_model[model]),
                "similarity": similarity,
                "matched_image_path": "",
                "image_type": LABEL_IMAGE_TYPE,
            }
            for similarity, model in image_ranking
        ]

        def merged_ranking(images):
            merged = main.merge_similar_search_results(
                images, candidates, maker, similar_models, catalog, hints, top_k=len(catalog)
            )
            return [(r["combined_score"], r["product"]["model_number"]) for r in merged]

        results.append(
            QueryResult(
                image=query.image,
                expected=query.model_number,
                ranks={
                    "text": pessimistic_rank(query.model_number, merged_ranking([])),
                    "image": pessimistic_rank(query.model_number, image_ranking),
                    "hybrid": pessimistic_rank(query.model_number, merged_ranking(image_results)),
                },
                has_registered_image=any(
                    m == normalize_model(query.model_number) for m, _ in registered
                ),
            )
        )

    return results


def top_k_rate(results: list[QueryResult], mode: str, k: int) -> Optional[float]:
    if not results:
        return None
    return sum(1 for r in results if r.ranks[mode] is not None and r.ranks[mode] <= k) / len(results)


def summarize(results: list[QueryResult]) -> dict:
    with_image = [r for r in results if r.has_registered_image]
    metrics = {"total": len(results), "with_registered_image": len(with_image)}

    for scope, rows in (("all", results), ("with_image", with_image)):
        for mode in MODES:
            for k in (1, 3):
                metrics[f"{scope}_{mode}_top{k}"] = top_k_rate(rows, mode, k)

    # テキストだけでは 1 位にならなかった写真を、併用で 1 位にできたか／逆に落としたか
    metrics["rescued"] = [
        r.image for r in results if r.ranks["text"] != 1 and r.ranks["hybrid"] == 1
    ]
    metrics["regressed"] = [
        r.image for r in results if r.ranks["text"] == 1 and r.ranks["hybrid"] != 1
    ]
    return metrics


def render_markdown(results: list[QueryResult], metrics: dict, dataset_name: str, catalog_size: int) -> str:
    def row(label, scope):
        cells = [
            f"{pct(metrics[f'{scope}_{mode}_top1'])} / {pct(metrics[f'{scope}_{mode}_top3'])}"
            for mode in MODES
        ]
        return f"| {label} | " + " | ".join(cells) + " |"

    lines = [
        f"# OCR と画像検索（CLIP）の併用評価（{dataset_name}）",
        "",
        f"- 問い合わせ写真: {metrics['total']} 枚（うち同じ商品の別写真が登録済み: {metrics['with_registered_image']} 枚）",
        f"- 登録済み商品: {catalog_size} 件",
        "- 各セルは「Top-1 / Top-3」の正解率",
        "",
        "| 対象 | テキスト（OCR+DB） | 画像のみ（CLIP） | 併用（アプリの挙動） |",
        "|---|---|---|---|",
        row("すべての写真", "all"),
        row("同じ商品の別写真が登録済みの写真", "with_image"),
        "",
        f"- 併用で新たに 1 位になった写真: {', '.join(metrics['rescued']) or 'なし'}",
        f"- 併用で 1 位から落ちた写真: {', '.join(metrics['regressed']) or 'なし'}",
        "",
        "## 写真ごとの順位",
        "",
        "| 画像 | 正解 | 画像登録 | テキスト | 画像のみ | 併用 |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        cells = [r.ranks[m] or "圏外" for m in MODES]
        lines.append(
            f"| {r.image} | {r.expected} | {'あり' if r.has_registered_image else 'なし'} | "
            + " | ".join(str(c) for c in cells)
            + " |"
        )
    return "\n".join(lines) + "\n"


def collect_features(dataset_dir: Path, cases: list[Case], main, cache_path: Optional[Path]) -> dict:
    """各写真の OCR テキストと CLIP 埋め込みを求める（OCR は遅いのでキャッシュできる）。"""
    from evaluation.evaluate_ocr import read_in_temp_copy

    cache: dict = {}
    if cache_path and cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))

    features = {}
    for case in cases:
        path = dataset_dir / case.image
        stamp = f"{path.stat().st_size}"
        cached = cache.get(case.image)

        if case.ocr_texts is not None:
            texts = case.ocr_texts
        elif cached and cached["stamp"] == stamp:
            texts = cached["texts"]
        else:
            texts = read_in_temp_copy(main, str(path))
            cache[case.image] = {"stamp": stamp, "texts": texts}

        features[case.image] = {
            "texts": texts,
            "embedding": main.normalize_embedding_vector(main.get_image_embedding(str(path))).ravel(),
        }

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    return features


def run(
    dataset_dir: Path,
    catalog_db: Optional[Path] = None,
    cache_path: Optional[Path] = None,
    min_similarity: Optional[float] = None,
    image_baseline: Optional[float] = None,
):
    root = tempfile.mkdtemp(prefix="sekou_navi_eval_")
    os.environ["SEKOU_DB_PATH"] = os.path.join(root, "eval.db")
    os.environ["SEKOU_IMAGE_DIR"] = os.path.join(root, "images")
    os.environ["SEKOU_TEMP_DIR"] = os.path.join(root, "temp_images")

    import main  # noqa: PLC0415

    if image_baseline is not None:
        main.IMAGE_SCORE_BASELINE = image_baseline

    cases = load_cases(dataset_dir)
    catalog = build_catalog(cases, catalog_db)
    features = collect_features(dataset_dir, cases, main, cache_path)
    results = evaluate_queries(cases, features, catalog, main, min_similarity)
    return results, summarize(results), len(catalog)


def main_cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--catalog-db", type=Path)
    parser.add_argument("--out", type=Path, default=Path("evaluation/results"))
    parser.add_argument(
        "--cache",
        type=Path,
        help="OCR 結果のキャッシュ（再実行を速くする。コードを変えたら消すこと）",
    )
    parser.add_argument(
        "--min-similarity",
        type=float,
        help="画像の類似度がこの値未満なら無視する（既定はアプリの MIN_SIMILARITY）",
    )
    parser.add_argument(
        "--image-baseline",
        type=float,
        help="画像の類似度から差し引く基準値（既定はアプリの IMAGE_SCORE_BASELINE）",
    )
    args = parser.parse_args()

    results, metrics, catalog_size = run(
        args.dataset, args.catalog_db, args.cache, args.min_similarity, args.image_baseline
    )
    args.out.mkdir(parents=True, exist_ok=True)
    name = f"{args.dataset.name}_hybrid"

    (args.out / f"{name}.json").write_text(
        json.dumps(
            {"metrics": metrics, "results": [asdict(r) for r in results]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    markdown = render_markdown(results, metrics, args.dataset.name, catalog_size)
    (args.out / f"{name}.md").write_text(markdown, encoding="utf-8")
    print(markdown)


if __name__ == "__main__":
    main_cli()
