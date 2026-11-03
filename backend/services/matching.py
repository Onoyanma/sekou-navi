"""OCR の結果・画像の類似度・登録済み商品を突き合わせ、商品の候補をスコア順に並べる。"""

import sqlite3
from difflib import SequenceMatcher

from sklearn.metrics.pairwise import cosine_similarity

from database import DB_PATH as DB_NAME
from services.embeddings import (
    blob_to_embedding,
    normalize_embedding_vector,
    rebuild_missing_image_embeddings,
)


IMAGE_SCORE_BASELINE = 0.7

# 統合スコアから「どれだけ信用してよいか」を 3 段階にする基準。
# 実写真 14 枚の評価では、型番が一致した正解は 330 点以上、間違った 1 位は 97 点以下だった。
# その間（100〜300）を「中」にしている。小さなデータからの目安なので、データが増えたら見直す。
CONFIDENCE_HIGH_SCORE = 300
CONFIDENCE_MEDIUM_SCORE = 100

IMAGE_TYPE_WEIGHTS = {
    "型番ラベル": 1.5,
    "全体写真": 1.2,
    "部品アップ": 1.1,
    "施工例": 0.7,
    "その他": 1.0,
}


def classify_confidence(combined_score, sources):
    """統合スコアと根拠から、結果の確度（high / medium / low）を返す。

    画像の類似だけでは別商品でも高く出るため、型番が一致した根拠がなければ high にしない。
    """
    if "model" in sources and combined_score >= CONFIDENCE_HIGH_SCORE:
        return "high"

    if combined_score >= CONFIDENCE_MEDIUM_SCORE:
        return "medium"

    return "low"


def fetch_all_products():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
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
            created_at
        FROM products
    """)

    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows


def find_similar_model_numbers(ocr_candidates, all_products, threshold=0.7):
    results = []

    for candidate, ocr_score in ocr_candidates[:15]:
        candidate_upper = candidate.upper()

        for product in all_products:
            db_model = str(product.get("model_number") or "").upper()
            if not db_model:
                continue

            similarity = SequenceMatcher(
                None,
                candidate_upper,
                db_model,
            ).ratio()

            if similarity >= threshold:
                results.append({
                    "product": product,
                    "ocr_candidate": candidate,
                    "similarity": similarity,
                    "ocr_score": ocr_score,
                })

    results.sort(
        key=lambda x: (x["similarity"], x["ocr_score"]),
        reverse=True,
    )
    return results[:10]


def score_product_from_ocr(product, ocr_candidates, detected_maker, product_name_hints):
    score = 0.0
    sources = []
    matched_candidate = ""

    db_model = str(product.get("model_number") or "").upper()
    db_maker = str(product.get("maker") or "")
    db_name = str(product.get("product_name") or "")
    db_memo = str(product.get("memo") or "")
    db_tags = str(product.get("tags") or "")

    if detected_maker and db_maker:
        if (
            detected_maker.lower() in db_maker.lower()
            or db_maker.lower() in detected_maker.lower()
        ):
            score += 28
            sources.append("maker")

    for candidate, ocr_score in ocr_candidates[:12]:
        candidate_upper = candidate.upper()
        if not db_model:
            continue

        if candidate_upper == db_model:
            score += 55 + ocr_score * 0.15
            sources.append("model")
            matched_candidate = candidate
        elif candidate_upper in db_model or db_model in candidate_upper:
            score += 35 + ocr_score * 0.1
            sources.append("model")
            matched_candidate = candidate
        else:
            similarity = SequenceMatcher(
                None,
                candidate_upper,
                db_model,
            ).ratio()
            if similarity >= 0.72:
                score += similarity * 45 + ocr_score * 0.1
                sources.append("model")
                matched_candidate = candidate

    for hint in product_name_hints:
        hint_upper = hint.upper()
        for field in (db_name, db_memo, db_tags):
            if not field:
                continue
            field_upper = field.upper()
            if hint_upper in field_upper:
                score += 22
                sources.append("name")
                break
            similarity = SequenceMatcher(None, hint_upper, field_upper).ratio()
            if similarity >= 0.55:
                score += similarity * 25
                sources.append("name")
                break

    return score, list(dict.fromkeys(sources)), matched_candidate


def product_row_to_result(product):
    image_path = product.get("image_path") or ""
    first_image = image_path.split(",")[0] if image_path else ""

    return {
        "id": product["id"],
        "maker": product.get("maker") or "",
        "product_name": product.get("product_name") or "",
        "model_number": product.get("model_number") or "",
        "category": product.get("category") or "",
        "memo": product.get("memo") or "",
        "tags": product.get("tags") or "",
        "install_url": product.get("install_url") or "",
        "official_url": product.get("official_url") or "",
        "image_path": first_image,
        "matched_image_path": "",
    }


def merge_similar_search_results(
    image_results,
    ocr_candidates,
    detected_maker,
    similar_model_results,
    all_products,
    product_name_hints,
    top_k=10,
):
    merged = {}

    def ensure_entry(product_id):
        if product_id not in merged:
            merged[product_id] = {
                "product": None,
                "similarity": 0.0,
                "combined_score": 0.0,
                "sources": [],
                "ocr_candidate": "",
                "matched_image_path": "",
                "image_type": "",
            }
        return merged[product_id]

    for item in image_results:
        product = item["product"]
        product_id = product["id"]
        entry = ensure_entry(product_id)
        entry["product"] = product

        image_type = item.get("image_type") or "その他"
        weight = IMAGE_TYPE_WEIGHTS.get(image_type, 1.0)
        # CLIP の類似度は、型番ラベルのように見た目が似た写真どうしだと別商品でも高く出る。
        # 基準値（IMAGE_SCORE_BASELINE）を超えた分だけを点数にして、似ているだけの商品が
        # 型番の一致を押しのけないようにする（0 なら類似度にそのまま比例）。
        # 型番ラベル写真 14 枚の評価で 0.6〜0.8 が同じ結果になる範囲だったので、中央付近の値にしている。
        normalized_similarity = max(0.0, item["similarity"] - IMAGE_SCORE_BASELINE) / (
            1.0 - IMAGE_SCORE_BASELINE
        )
        image_score = normalized_similarity * 50 * weight

        entry["combined_score"] += image_score
        entry["similarity"] = max(entry["similarity"], item["similarity"])
        entry["matched_image_path"] = item.get("matched_image_path") or ""
        entry["image_type"] = image_type

        if "image" not in entry["sources"]:
            entry["sources"].append("image")

        if detected_maker and product.get("maker"):
            if detected_maker.lower() in product["maker"].lower():
                entry["combined_score"] += 20
                if "maker" not in entry["sources"]:
                    entry["sources"].append("maker")

        for candidate, ocr_score in ocr_candidates[:8]:
            model_number = str(product.get("model_number") or "").lower()
            if candidate.lower() in model_number:
                entry["combined_score"] += 30
                entry["ocr_candidate"] = candidate
                if "model" not in entry["sources"]:
                    entry["sources"].append("model")
            elif model_number and model_number in candidate.lower():
                entry["combined_score"] += 20
                entry["ocr_candidate"] = candidate
                if "model" not in entry["sources"]:
                    entry["sources"].append("model")

    for match in similar_model_results:
        product = match["product"]
        product_id = product["id"]
        entry = ensure_entry(product_id)

        if entry["product"] is None:
            entry["product"] = product_row_to_result(product)

        fuzzy_score = match["similarity"] * 100 + match["ocr_score"] * 0.3
        entry["combined_score"] += fuzzy_score
        entry["ocr_candidate"] = match.get("ocr_candidate") or entry["ocr_candidate"]
        if "model" not in entry["sources"]:
            entry["sources"].append("model")

    for product in all_products:
        text_score, sources, matched_candidate = score_product_from_ocr(
            product,
            ocr_candidates,
            detected_maker,
            product_name_hints,
        )
        if text_score < 18:
            continue

        product_id = product["id"]
        entry = ensure_entry(product_id)

        if entry["product"] is None:
            entry["product"] = product_row_to_result(product)

        entry["combined_score"] += text_score
        for source in sources:
            if source not in entry["sources"]:
                entry["sources"].append(source)
        if matched_candidate and not entry["ocr_candidate"]:
            entry["ocr_candidate"] = matched_candidate

    results = [
        entry for entry in merged.values() if entry["product"] is not None
    ]
    results.sort(key=lambda x: x["combined_score"], reverse=True)

    for entry in results:
        entry["confidence"] = classify_confidence(
            entry["combined_score"], entry["sources"]
        )

    return results[:top_k]


MIN_SIMILARITY = 0.25


def format_similar_product(row_dict):
    matched_image_path = row_dict.get("image_path") or ""
    product_image_path = row_dict.get("product_image_path") or ""
    display_image_path = matched_image_path

    if not display_image_path and product_image_path:
        display_image_path = product_image_path.split(",")[0]

    return {
        "id": row_dict["id"],
        "maker": row_dict.get("maker") or "",
        "product_name": row_dict.get("product_name") or "",
        "model_number": row_dict.get("model_number") or "",
        "category": row_dict.get("category") or "",
        "memo": row_dict.get("memo") or "",
        "tags": row_dict.get("tags") or "",
        "install_url": row_dict.get("install_url") or "",
        "official_url": row_dict.get("official_url") or "",
        "image_path": display_image_path,
        "matched_image_path": matched_image_path,
    }


def fetch_embedded_product_images():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT
            product_images.id AS image_id,
            product_images.product_id,
            product_images.image_path,
            product_images.image_type,
            product_images.image_embedding,
            products.id,
            products.maker,
            products.product_name,
            products.model_number,
            products.category,
            products.manual_url,
            products.install_url,
            products.official_url,
            products.memo,
            products.tags,
            products.image_path AS product_image_path,
            products.created_at
        FROM product_images
        JOIN products
        ON product_images.product_id = products.id
        WHERE product_images.image_embedding IS NOT NULL
    """)

    rows = cur.fetchall()
    conn.close()

    return rows


def compute_similar_results(query_embeddings, top_k=5):
    rows = fetch_embedded_product_images()

    if not rows:
        rebuild_missing_image_embeddings()
        rows = fetch_embedded_product_images()

    best_results = {}

    for row in rows:
        row_dict = dict(row)

        stored_embedding = blob_to_embedding(row_dict["image_embedding"])

        if stored_embedding is None:
            continue

        stored_embedding = normalize_embedding_vector(stored_embedding)

        similarity = max(
            float(cosine_similarity(query_embedding, stored_embedding)[0][0])
            for query_embedding in query_embeddings
        )

        if similarity < MIN_SIMILARITY:
            continue

        product_id = row_dict["product_id"]

        row_dict.pop("image_embedding", None)

        formatted = {
            "product": format_similar_product(row_dict),
            "similarity": similarity,
            "matched_image_path": row_dict.get("image_path") or "",
            "image_type": row_dict.get("image_type") or "その他",
        }

        if product_id not in best_results:
            best_results[product_id] = formatted
        elif similarity > best_results[product_id]["similarity"]:
            best_results[product_id] = formatted

    return sorted(
        best_results.values(),
        key=lambda x: x["similarity"],
        reverse=True,
    )[:top_k]
