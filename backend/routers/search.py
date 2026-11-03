"""商品の検索・入力補完・検索用ベクトルの再構築。"""

import sqlite3
import traceback

from fastapi import APIRouter, HTTPException

from database import DB_PATH as DB_NAME
from services.barcode import search_products_by_barcode
from services.embeddings import (
    rebuild_missing_image_embeddings,
    rebuild_missing_product_text_embeddings,
)
from services.search import (
    MIN_SEMANTIC_SIMILARITY,
    fuzzy_score,
    keyword_search_products,
    merge_hybrid_search_results,
    semantic_search_products,
)

router = APIRouter()


@router.post("/embeddings/rebuild")
def rebuild_embeddings():
    try:
        updated = rebuild_missing_image_embeddings()
        return {"updated": updated}
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ai-search")
def ai_search(
    q: str = "",
    mode: str = "hybrid",
    limit: int = 20,
):
    """
    mode:
      - keyword: 従来のキーワード一致
      - semantic: 自然文の意味検索（テキスト埋め込み）
      - hybrid: 両方を統合（デフォルト）
    """
    query = q.strip()
    allowed_modes = {"keyword", "semantic", "hybrid"}

    if mode not in allowed_modes:
        raise HTTPException(
            status_code=400,
            detail="mode は keyword, semantic, hybrid のいずれかです",
        )

    if not query:
        return {"results": [], "mode": mode, "query": query}

    try:
        if mode == "keyword":
            results = keyword_search_products(query)
        elif mode == "semantic":
            results = semantic_search_products(query, limit=limit)
        else:
            keyword_results = keyword_search_products(query)
            semantic_results = semantic_search_products(query, limit=limit)
            results = merge_hybrid_search_results(
                keyword_results,
                semantic_results,
            )

        return {
            "results": results[:limit],
            "mode": mode,
            "query": query,
            "min_semantic_similarity": MIN_SEMANTIC_SIMILARITY,
        }
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/embeddings/rebuild-text")
def rebuild_text_embeddings():
    try:
        updated = rebuild_missing_product_text_embeddings()
        return {"updated": updated}
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/barcode-search")
def barcode_search(code: str = ""):
    if not code.strip():
        raise HTTPException(status_code=400, detail="code が必要です")

    try:
        return search_products_by_barcode(code)
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/field-suggestions")
def field_suggestions(
    field: str = "maker",
    q: str = "",
    maker: str = "",
    limit: int = 8,
):
    if field not in ("maker", "product_name"):
        raise HTTPException(
            status_code=400,
            detail="field は maker または product_name を指定してください",
        )

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT maker, product_name
        FROM products
    """)

    rows = cur.fetchall()
    conn.close()

    ignore_values = {"", "未登録"}
    q_upper = q.strip().upper()
    maker_upper = maker.strip().upper()
    scored: dict[str, float] = {}

    for row in rows:
        row_dict = dict(row)
        row_maker = str(row_dict.get("maker") or "").strip()
        value = str(row_dict.get(field) or "").strip()

        if not value or value in ignore_values:
            continue

        if field == "product_name" and maker_upper:
            if maker_upper not in row_maker.upper():
                continue

        value_upper = value.upper()

        if not q_upper:
            score = 50.0
        elif value_upper.startswith(q_upper):
            score = 100.0 + len(q_upper)
        elif q_upper in value_upper:
            score = 80.0
        else:
            similarity = fuzzy_score(q_upper, value_upper)
            if similarity < 55:
                continue
            score = similarity

        scored[value] = max(scored.get(value, 0.0), score)

    suggestions = sorted(
        scored.items(),
        key=lambda item: (item[1], item[0]),
        reverse=True,
    )

    return {
        "field": field,
        "suggestions": [value for value, _ in suggestions[:limit]],
    }


@router.get("/search-suggestions")
def search_suggestions(q: str = ""):
    if not q:
        return {"suggestions": []}

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row

    cur = conn.cursor()

    cur.execute("""
        SELECT
            maker,
            product_name,
            model_number,
            category,
            tags
        FROM products
    """)

    rows = cur.fetchall()
    conn.close()

    q_upper = q.upper()
    suggestions = set()

    for row in rows:
        values = [
            row["maker"],
            row["product_name"],
            row["model_number"],
            row["category"],
            row["tags"]
        ]

        for value in values:
            if not value:
                continue

            value_text = str(value)

            # タグはカンマ区切りなので分解
            parts = value_text.split(",")

            for part in parts:
                part = part.strip()

                if not part:
                    continue

                if q_upper in part.upper():
                    suggestions.add(part)

                elif fuzzy_score(q_upper, part.upper()) >= 60:
                    suggestions.add(part)

    return {
        "suggestions": list(suggestions)[:8]
    }
