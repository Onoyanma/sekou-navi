"""キーワード検索・意味検索・あいまい検索。"""

import sqlite3
from difflib import SequenceMatcher

from sklearn.metrics.pairwise import cosine_similarity

from database import DB_PATH as DB_NAME
from services.embeddings import (
    blob_to_embedding,
    build_product_text_embedding_blob,
    get_text_model,
    normalize_embedding_vector,
)


MIN_SEMANTIC_SIMILARITY = 0.32


def fetch_all_product_rows():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            id,
            maker,
            product_name,
            model_number,
            category,
            image_path,
            manual_url,
            install_url,
            official_url,
            memo,
            tags,
            text_embedding,
            created_at
        FROM products
        """
    )

    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows


def public_product(row_dict):
    """API レスポンス用に、埋め込みベクトル（バイナリ）を除いた商品情報を返す。"""
    return {
        key: value
        for key, value in row_dict.items()
        if key not in ("text_embedding", "image_embedding")
    }


def keyword_search_products(query: str):
    rows = fetch_all_product_rows()
    keywords = query.upper().replace("　", " ").split()
    results = []

    for row_dict in rows:
        score = 0
        matched_all_keywords = True

        for keyword in keywords:
            keyword_score = 0

            maker_score = fuzzy_score(keyword, row_dict.get("maker", ""))
            product_name_score = fuzzy_score(
                keyword, row_dict.get("product_name", "")
            )
            model_score = fuzzy_score(keyword, row_dict.get("model_number", ""))
            category_score = fuzzy_score(keyword, row_dict.get("category", ""))
            tags_score = fuzzy_score(keyword, row_dict.get("tags", ""))
            memo_score = fuzzy_score(keyword, row_dict.get("memo", ""))

            if maker_score >= 60:
                keyword_score += maker_score * 0.8
            if product_name_score >= 50:
                keyword_score += product_name_score * 0.7
            if model_score >= 55:
                keyword_score += model_score * 1.2
            if category_score >= 60:
                keyword_score += category_score * 0.7
            if tags_score >= 60:
                keyword_score += tags_score * 0.5
            if memo_score >= 70:
                keyword_score += memo_score * 0.3

            if keyword_score == 0:
                matched_all_keywords = False
                break

            score += keyword_score

        if matched_all_keywords and score > 0:
            results.append({
                "product": public_product(row_dict),
                "score": round(score, 1),
                "keyword_score": round(score, 1),
                "semantic_score": 0,
                "similarity": 0,
                "sources": ["keyword"],
            })

    results.sort(key=lambda item: item["score"], reverse=True)
    return results


def semantic_search_products(query: str, limit: int = 20):
    rows = fetch_all_product_rows()

    if not rows:
        return []

    query = query.strip()
    model = get_text_model()
    query_embedding = normalize_embedding_vector(
        model.encode(query, normalize_embeddings=True)
    )

    missing_ids = []
    results = []

    for row_dict in rows:
        embedding = blob_to_embedding(row_dict.get("text_embedding"))

        if embedding is None:
            missing_ids.append(row_dict["id"])
            embedding_blob = build_product_text_embedding_blob(row_dict)
            if embedding_blob:
                conn = sqlite3.connect(DB_NAME)
                cur = conn.cursor()
                cur.execute(
                    "UPDATE products SET text_embedding = ? WHERE id = ?",
                    (embedding_blob, row_dict["id"]),
                )
                conn.commit()
                conn.close()
                embedding = blob_to_embedding(embedding_blob)

        if embedding is None:
            continue

        stored_embedding = normalize_embedding_vector(embedding)
        similarity = float(
            cosine_similarity(query_embedding, stored_embedding)[0][0]
        )

        if similarity < MIN_SEMANTIC_SIMILARITY:
            continue

        semantic_score = round(similarity * 100, 1)

        results.append({
            "product": public_product(row_dict),
            "score": semantic_score,
            "keyword_score": 0,
            "semantic_score": semantic_score,
            "similarity": round(similarity, 4),
            "sources": ["semantic"],
        })

    results.sort(
        key=lambda item: (item["similarity"], item["score"]),
        reverse=True,
    )
    return results[:limit]


def merge_hybrid_search_results(keyword_results, semantic_results):
    merged = {}

    for item in keyword_results:
        product_id = item["product"]["id"]
        normalized_keyword = min(item["score"] / 120, 1) * 100
        merged[product_id] = {
            **item,
            "score": round(normalized_keyword * 0.45, 1),
            "sources": ["keyword"],
        }

    for item in semantic_results:
        product_id = item["product"]["id"]
        semantic_part = item["semantic_score"] * 0.55

        if product_id in merged:
            entry = merged[product_id]
            entry["semantic_score"] = item["semantic_score"]
            entry["similarity"] = item["similarity"]
            entry["score"] = round(entry["score"] + semantic_part, 1)
            if "semantic" not in entry["sources"]:
                entry["sources"].append("semantic")
        else:
            merged[product_id] = {
                **item,
                "score": round(semantic_part, 1),
                "keyword_score": 0,
                "sources": ["semantic"],
            }

    combined = list(merged.values())
    combined.sort(key=lambda item: item["score"], reverse=True)
    return combined


def fuzzy_score(keyword, target):
    keyword = str(keyword).upper()
    target = str(target).upper()

    if not keyword or not target:
        return 0

    if keyword in target:
        return 100

    similarity = SequenceMatcher(
        None,
        keyword,
        target
    ).ratio()

    return similarity * 100
