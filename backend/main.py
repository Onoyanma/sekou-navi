from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import shutil
from PIL import Image, ImageEnhance, ImageFilter
import easyocr
import re
import os
import sqlite3
from fastapi import HTTPException
import traceback
import pickle
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from difflib import SequenceMatcher
from fastapi import Body
from typing import List, Optional
import json
from urllib.parse import urlparse, parse_qs, unquote

import ai as product_ai
from database import (
    BASE_DIR,
    DB_PATH as DB_NAME,
    IMAGE_DIR,
    TEMP_DIR,
    ensure_storage_dirs,
    init_db,
    unique_filename,
)

app = FastAPI(title="施工ナビ API")

# 初回起動時（DB・画像フォルダがまだ無い場合）でも動くように先に用意する
ensure_storage_dirs()
init_db()

app.mount(
    "/images",
    StaticFiles(directory=IMAGE_DIR),
    name="images"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.environ.get(
            "SEKOU_CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "施工ナビ API"}


@app.get("/products")
def get_products():
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
        ORDER BY created_at DESC
    """)

    rows = cur.fetchall()

    conn.close()

    return [dict(row) for row in rows]


@app.get("/products/summary")
def get_products_summary(limit: int = 6):
    limit = max(1, min(limit, 20))

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS count FROM products")
    count = cur.fetchone()["count"]

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
            created_at
        FROM products
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()

    return {"count": count, "recent": [dict(row) for row in rows]}


@app.get("/products/{product_id}")
def get_product(product_id: int):
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
        WHERE id = ?
    """, (product_id,))

    row = cur.fetchone()
    conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail="商品が見つかりません")

    return dict(row)

class ProductCreate(BaseModel):
    maker: str
    product_name: str
    model_number: str
    category: str
    memo: str = ""
    tags: str = ""
    manual_url: str = ""
    install_url: str = ""
    official_url: str = ""


class ProductAutocompleteRequest(BaseModel):
    model_number: str = ""
    url: str = ""


class ProductUpdate(BaseModel):
    maker: str
    product_name: str
    model_number: str
    category: str
    memo: str = ""
    tags: str = ""
    manual_url: str = ""
    install_url: str = ""
    official_url: str = ""


def sync_product_image_paths(product_id: int):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT image_path
        FROM product_images
        WHERE product_id = ?
        ORDER BY created_at ASC
        """,
        (product_id,),
    )

    paths = [row[0] for row in cur.fetchall() if row[0]]
    joined_paths = ",".join(paths)

    cur.execute(
        "UPDATE products SET image_path = ? WHERE id = ?",
        (joined_paths, product_id),
    )

    conn.commit()
    conn.close()

    return joined_paths


def build_auto_tagged_product_fields(product) -> tuple[str, list[str]]:
    row = {
        "maker": product.maker,
        "product_name": product.product_name,
        "model_number": product.model_number,
        "category": product.category,
        "memo": product.memo,
        "official_url": getattr(product, "official_url", "") or "",
        "manual_url": getattr(product, "manual_url", "") or "",
        "install_url": getattr(product, "install_url", "") or "",
    }
    return product_ai.apply_auto_tags(row, product.tags or "")


@app.post("/products")
def create_product(product: ProductCreate):
    final_tags, added_tags = build_auto_tagged_product_fields(product)

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO products
        (
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
            image_embedding,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
    """, (
        product.maker,
        product.product_name,
        product.model_number,
        product.category,
        "",
        product.manual_url,
        product.install_url,
        product.official_url,
        product.memo,
        final_tags,
        None
    ))

    conn.commit()

    product_id = cur.lastrowid
    if product_id is None:
        conn.close()
        raise HTTPException(status_code=500, detail="商品IDの取得に失敗しました")

    conn.close()

    save_product_text_embedding(
        product_id,
        {
            "id": product_id,
            "maker": product.maker,
            "product_name": product.product_name,
            "model_number": product.model_number,
            "category": product.category,
            "memo": product.memo,
            "tags": final_tags,
        },
    )

    return {
        "message": "商品を登録しました",
        "id": product_id,
        "tags": final_tags,
        "auto_tags_added": added_tags,
    }

@app.post("/products/{product_id}/images")
async def upload_product_image(
    product_id: int,
    file: UploadFile = File(...)
):
    os.makedirs(IMAGE_DIR, exist_ok=True)

    file_name = unique_filename(file.filename, prefix=f"{product_id}_")
    image_path = os.path.join(IMAGE_DIR, file_name)

    with open(image_path, "wb") as f:
        content = await file.read()
        f.write(content)

    db_image_path = f"images/{file_name}"

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute(
        "SELECT image_path FROM products WHERE id = ?",
        (product_id,)
    )

    row = cur.fetchone()

    current_image_path = ""

    if row and row[0]:
        current_image_path = row[0]

    if current_image_path:
        new_image_path = f"{current_image_path},{db_image_path}"
    else:
        new_image_path = db_image_path

    cur.execute("""
        UPDATE products
        SET image_path = ?
        WHERE id = ?
    """, (
        new_image_path,
        product_id
    ))

    embedding_blob = build_embedding_blob(db_image_path)

    cur.execute("""
        INSERT INTO product_images
        (
            product_id,
            image_path,
            image_type,
            image_embedding,
            created_at
        )
        VALUES (?, ?, ?, ?, datetime('now', 'localtime'))
    """, (
        product_id,
        db_image_path,
        "その他",
        embedding_blob
    ))

    conn.commit()
    conn.close()

    return {
        "message": "画像をアップロードしました",
        "image_path": db_image_path,
        "embedding_saved": embedding_blob is not None
    }


@app.put("/products/{product_id}")
def update_product(product_id: int, product: ProductUpdate):
    final_tags, added_tags = build_auto_tagged_product_fields(product)

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("SELECT id FROM products WHERE id = ?", (product_id,))
    row = cur.fetchone()

    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="商品が見つかりません")

    cur.execute("""
        UPDATE products
        SET
            maker = ?,
            product_name = ?,
            model_number = ?,
            category = ?,
            manual_url = ?,
            install_url = ?,
            official_url = ?,
            memo = ?,
            tags = ?
        WHERE id = ?
    """, (
        product.maker,
        product.product_name,
        product.model_number,
        product.category,
        product.manual_url,
        product.install_url,
        product.official_url,
        product.memo,
        final_tags,
        product_id,
    ))

    conn.commit()
    conn.close()

    save_product_text_embedding(
        product_id,
        {
            "id": product_id,
            "maker": product.maker,
            "product_name": product.product_name,
            "model_number": product.model_number,
            "category": product.category,
            "memo": product.memo,
            "tags": final_tags,
        },
    )

    saved = get_product(product_id)

    return {
        **saved,
        "auto_tags_added": added_tags,
    }


@app.post("/products/auto-tags/rebuild")
def rebuild_all_product_auto_tags():
    """全商品のタグをAIで再生成する（既存タグは保持してマージ）。"""
    products = fetch_all_products()
    updated = 0

    for product in products:
        product_id = product["id"]
        final_tags, _ = product_ai.apply_auto_tags(
            product,
            product.get("tags") or "",
        )

        if final_tags == (product.get("tags") or ""):
            continue

        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        cur.execute(
            "UPDATE products SET tags = ? WHERE id = ?",
            (final_tags, product_id),
        )
        conn.commit()
        conn.close()

        save_product_text_embedding(
            product_id,
            {**product, "tags": final_tags},
        )
        updated += 1

    return {"updated": updated, "total": len(products)}


@app.post("/products/{product_id}/auto-tags")
def refresh_product_auto_tags(product_id: int):
    """既存商品のタグをAIで再生成し、既存タグとマージする。"""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            id, maker, product_name, model_number, category,
            memo, tags, official_url, manual_url, install_url
        FROM products
        WHERE id = ?
        """,
        (product_id,),
    )
    row = cur.fetchone()
    conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail="商品が見つかりません")

    product = dict(row)
    final_tags, added_tags = product_ai.apply_auto_tags(
        product,
        product.get("tags") or "",
    )

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        "UPDATE products SET tags = ? WHERE id = ?",
        (final_tags, product_id),
    )
    conn.commit()
    conn.close()

    save_product_text_embedding(
        product_id,
        {**product, "tags": final_tags},
    )

    return {
        "id": product_id,
        "tags": final_tags,
        "auto_tags_added": added_tags,
    }


@app.delete("/products/{product_id}")
def delete_product(product_id: int):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("SELECT id FROM products WHERE id = ?", (product_id,))
    if cur.fetchone() is None:
        conn.close()
        raise HTTPException(status_code=404, detail="商品が見つかりません")

    cur.execute(
        "SELECT image_path FROM product_images WHERE product_id = ?",
        (product_id,),
    )
    image_rows = cur.fetchall()

    for (db_image_path,) in image_rows:
        file_path = resolve_image_file_path(db_image_path)
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

    cur.execute(
        "SELECT image_path FROM products WHERE id = ?",
        (product_id,),
    )
    product_row = cur.fetchone()
    if product_row and product_row[0]:
        for legacy_path in str(product_row[0]).split(","):
            file_path = resolve_image_file_path(legacy_path.strip())
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass

    cur.execute(
        "DELETE FROM product_images WHERE product_id = ?",
        (product_id,),
    )
    cur.execute("DELETE FROM products WHERE id = ?", (product_id,))

    conn.commit()
    conn.close()

    return {"message": "商品を削除しました", "id": product_id}


@app.get("/products/{product_id}/images")
def get_product_images(product_id: int):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT id FROM products WHERE id = ?", (product_id,))
    if cur.fetchone() is None:
        conn.close()
        raise HTTPException(status_code=404, detail="商品が見つかりません")

    cur.execute("""
        SELECT id, product_id, image_path, image_type, created_at
        FROM product_images
        WHERE product_id = ?
        ORDER BY created_at DESC
    """, (product_id,))

    rows = cur.fetchall()
    conn.close()

    return [dict(row) for row in rows]


@app.delete("/products/{product_id}/images/{image_id}")
def delete_product_image(product_id: int, image_id: int):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT image_path
        FROM product_images
        WHERE id = ? AND product_id = ?
        """,
        (image_id, product_id),
    )

    row = cur.fetchone()

    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="画像が見つかりません")

    db_image_path = row[0]
    file_path = resolve_image_file_path(db_image_path)

    if file_path and os.path.exists(file_path):
        os.remove(file_path)

    cur.execute(
        "DELETE FROM product_images WHERE id = ? AND product_id = ?",
        (image_id, product_id),
    )

    conn.commit()
    conn.close()

    image_path = sync_product_image_paths(product_id)

    return {
        "message": "画像を削除しました",
        "image_path": image_path,
    }


_ocr_reader = None


def get_ocr_reader():
    global _ocr_reader

    if _ocr_reader is None:
        _ocr_reader = easyocr.Reader(["en", "ja"], gpu=False)

    return _ocr_reader


def preprocess_image_for_ocr(image_path):
    image = Image.open(image_path)

    image = image.convert("L")

    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(2.0)

    image = image.filter(ImageFilter.SHARPEN)

    width, height = image.size
    image = image.resize((width * 2, height * 2))

    base, ext = os.path.splitext(image_path)
    processed_path = f"{base}_processed{ext}"

    image.save(processed_path)

    return processed_path


def extract_text_from_image(image_path):
    processed_path = preprocess_image_for_ocr(image_path)

    results = get_ocr_reader().readtext(
        processed_path,
        detail=0,
        paragraph=False,
        text_threshold=0.3,
        low_text=0.2,
        link_threshold=0.3
    )

    if not results:
        results = get_ocr_reader().readtext(
            image_path,
            detail=0,
            paragraph=False,
            text_threshold=0.3,
            low_text=0.2,
            link_threshold=0.3
        )

    return results

def normalize_ocr_text(text):
    replacements = {
        "Ｏ": "O",
        "０": "0",
        "１": "1",
        "Ｉ": "I",
        "ｌ": "L",
        "５": "5",
        "Ｓ": "S",
        "８": "8",
        "Ｂ": "B",
        "２": "2",
        "Ｚ": "Z"
    }

    for wrong, correct in replacements.items():
        text = text.replace(wrong, correct)

    return text


def generate_ocr_variants(text):
    replacements = {
        "O": ["0"],
        "0": ["O"],
        "I": ["1", "L"],
        "L": ["1", "I"],
        "1": ["I", "L"],
        "S": ["5"],
        "5": ["S"],
        "B": ["8"],
        "8": ["B"],
        "Z": ["2"],
        "2": ["Z"]
    }

    variants = {text}

    for i, char in enumerate(text):
        upper_char = char.upper()

        if upper_char in replacements:
            for replacement in replacements[upper_char]:
                new_text = text[:i] + replacement + text[i + 1:]
                variants.add(new_text)

    return list(variants)

def extract_model_candidates(text_list):
    scored_candidates = {}

    ignore_words = {
        "TOTO", "LIXIL", "PANASONIC", "YKK", "DAIKEN", "INAX",
        "MADE", "JAPAN", "MODEL", "TYPE",
        "品番", "型番", "製造", "取扱", "説明書"
    }

    for text in text_list:
        cleaned = text.strip()
        cleaned = normalize_ocr_text(cleaned)
        cleaned = cleaned.replace(" ", "")
        cleaned = cleaned.replace("　", "")
        cleaned = cleaned.replace("ー", "-")
        cleaned = cleaned.replace("－", "-")
        cleaned = cleaned.replace("―", "-")

        matches = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-_/.]{3,}", cleaned)

        for match in matches:
            match = match.strip(".,:;()[]{}<>")
            upper_match = match.upper()

            if upper_match in ignore_words:
                continue

            if len(match) < 4:
                continue

            if len(match) > 25:
                continue

            if match.isdigit():
                continue

            if match.isalpha():
                continue

            score = 0

            has_alpha = any(c.isalpha() for c in match)
            has_digit = any(c.isdigit() for c in match)

            if has_alpha and has_digit:
                score += 50

            if "-" in match:
                score += 15

            if "/" in match:
                score += 10

            if 5 <= len(match) <= 15:
                score += 15

            if len(match) >= 8:
                score += 5

            digit_count = sum(c.isdigit() for c in match)
            alpha_count = sum(c.isalpha() for c in match)

            if digit_count >= 2:
                score += 10

            if alpha_count >= 2:
                score += 5

            variants = generate_ocr_variants(upper_match)

            for variant in variants:
                variant_score = score

                if variant != upper_match:
                    variant_score -= 10

                if variant_score < 0:
                    variant_score = 0

                if variant not in scored_candidates:
                    scored_candidates[variant] = variant_score
                else:
                    scored_candidates[variant] = max(
                        scored_candidates[variant],
                        variant_score
                    )

    sorted_candidates = sorted(
        scored_candidates.items(),
        key=lambda x: x[1],
        reverse=True
    )

    return sorted_candidates


MAKER_ALIASES = {
    "TOTO": ["TOTO"],
    "LIXIL": ["LIXIL", "INAX"],
    "Panasonic": ["PANASONIC", "NATIONAL"],
    "YKK AP": ["YKK", "YKKAP", "YKK AP"],
    "DAIKEN": ["DAIKEN", "大建"],
    "クリナップ": ["CLEANUP", "クリナップ"],
    "タカラスタンダード": ["TAKARA", "タカラ"],
    "三菱電機": ["MITSUBISHI", "三菱"],
    "日立": ["HITACHI", "日立"],
    "リンナイ": ["RINNAI", "リンナイ"],
    "ノーリツ": ["NORITZ", "ノーリツ"],
}

IMAGE_TYPE_WEIGHTS = {
    "型番ラベル": 1.5,
    "全体写真": 1.2,
    "部品アップ": 1.1,
    "施工例": 0.7,
    "その他": 1.0,
}


def detect_maker_from_text(text_list):
    joined_text = " ".join(text_list).upper()

    for maker, aliases in MAKER_ALIASES.items():
        for alias in aliases:
            if alias.upper() in joined_text:
                return maker

    return ""


def extract_product_name_hints(text_list):
    hints = []
    seen = set()

    for text in text_list:
        cleaned = text.strip()
        if len(cleaned) < 2:
            continue

        compact = cleaned.replace(" ", "").replace("　", "")
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9\-_/.]{3,}", compact):
            continue

        if cleaned.upper() in {
            "TOTO", "LIXIL", "PANASONIC", "INAX", "MADE", "JAPAN",
            "MODEL", "TYPE", "品番", "型番",
        }:
            continue

        if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", cleaned):
            key = cleaned
        elif re.search(r"[A-Za-z]{3,}", cleaned) and len(cleaned) >= 4:
            if re.fullmatch(r"[A-Z0-9\-]+", cleaned.upper()):
                continue
            key = cleaned.upper()
        else:
            continue

        if key not in seen:
            seen.add(key)
            hints.append(cleaned)

    return hints[:8]


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
        image_score = item["similarity"] * 50 * weight

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
    return results[:top_k]


_image_model = None

text_model = None
TEXT_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

MIN_SIMILARITY = 0.25
MIN_SEMANTIC_SIMILARITY = 0.32


def embedding_to_blob(embedding):
    return pickle.dumps(np.asarray(embedding, dtype=np.float32))


def blob_to_embedding(blob):
    if blob is None:
        return None

    return pickle.loads(blob)


def resolve_image_file_path(db_image_path):
    if not db_image_path:
        return None

    candidates = [
        db_image_path,
        os.path.join(BASE_DIR, "..", db_image_path),
        os.path.join(IMAGE_DIR, os.path.basename(db_image_path)),
    ]

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate

    return None


def get_image_model():
    global _image_model

    if _image_model is None:
        _image_model = SentenceTransformer("clip-ViT-B-32")

    return _image_model


def get_image_embedding(image_path):
    file_path = resolve_image_file_path(image_path) or image_path
    image = Image.open(file_path).convert("RGB")
    embedding = get_image_model().encode(image, normalize_embeddings=True)

    return embedding


def normalize_embedding_vector(embedding):
    vector = np.asarray(embedding, dtype=np.float32).reshape(1, -1)
    norm = np.linalg.norm(vector)

    if norm == 0:
        return vector

    return vector / norm


def get_text_model():
    global text_model

    if text_model is None:
        text_model = SentenceTransformer(TEXT_MODEL_NAME)

    return text_model


def build_product_search_text(row_dict):
    return " ".join(
        [
            str(row_dict.get("maker") or ""),
            str(row_dict.get("product_name") or ""),
            str(row_dict.get("model_number") or ""),
            str(row_dict.get("category") or ""),
            str(row_dict.get("tags") or ""),
            str(row_dict.get("memo") or ""),
        ]
    ).strip()


def build_product_text_embedding_blob(row_dict):
    text = build_product_search_text(row_dict)

    if not text:
        return None

    try:
        model = get_text_model()
        embedding = model.encode(text, normalize_embeddings=True)
        return embedding_to_blob(embedding)
    except Exception as e:
        print(f"text embedding failed for product {row_dict.get('id')}: {e}")
        return None


def ensure_text_embedding_column():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(products)")
    columns = [row[1] for row in cur.fetchall()]

    if "text_embedding" not in columns:
        cur.execute("ALTER TABLE products ADD COLUMN text_embedding BLOB")

    conn.commit()
    conn.close()


def save_product_text_embedding(product_id: int, row_dict=None):
    ensure_text_embedding_column()

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if row_dict is None:
        cur.execute(
            """
            SELECT
                id, maker, product_name, model_number,
                category, memo, tags
            FROM products
            WHERE id = ?
            """,
            (product_id,),
        )
        row = cur.fetchone()
        if row is None:
            conn.close()
            return
        row_dict = dict(row)

    embedding_blob = build_product_text_embedding_blob(row_dict)

    cur.execute(
        "UPDATE products SET text_embedding = ? WHERE id = ?",
        (embedding_blob, product_id),
    )

    conn.commit()
    conn.close()


def rebuild_missing_product_text_embeddings():
    ensure_text_embedding_column()

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            id, maker, product_name, model_number,
            category, memo, tags
        FROM products
        WHERE text_embedding IS NULL
        """
    )

    rows = cur.fetchall()
    updated = 0

    for row in rows:
        row_dict = dict(row)
        embedding_blob = build_product_text_embedding_blob(row_dict)

        if embedding_blob is None:
            continue

        cur.execute(
            "UPDATE products SET text_embedding = ? WHERE id = ?",
            (embedding_blob, row_dict["id"]),
        )
        updated += 1

    conn.commit()
    conn.close()

    return updated


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


def build_embedding_blob(db_image_path):
    file_path = resolve_image_file_path(db_image_path)

    if not file_path:
        return None

    try:
        embedding = get_image_embedding(file_path)
        return embedding_to_blob(embedding)
    except Exception as e:
        print(f"embedding failed for {db_image_path}: {e}")
        return None


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


def rebuild_missing_image_embeddings():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        SELECT id, image_path
        FROM product_images
        WHERE image_embedding IS NULL
    """)

    rows = cur.fetchall()
    updated = 0

    for image_id, image_path in rows:
        embedding_blob = build_embedding_blob(image_path)

        if embedding_blob is None:
            continue

        cur.execute(
            "UPDATE product_images SET image_embedding = ? WHERE id = ?",
            (embedding_blob, image_id)
        )
        updated += 1

    conn.commit()
    conn.close()

    return updated


@app.on_event("startup")
def startup_rebuild_embeddings():
    try:
        updated_images = rebuild_missing_image_embeddings()
        if updated_images:
            print(f"Rebuilt {updated_images} image embeddings")

        updated_text = rebuild_missing_product_text_embeddings()
        if updated_text:
            print(f"Rebuilt {updated_text} product text embeddings")
    except Exception as e:
        print(f"embedding rebuild skipped: {e}")


@app.post("/embeddings/rebuild")
def rebuild_embeddings():
    try:
        updated = rebuild_missing_image_embeddings()
        return {"updated": updated}
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

def remove_temp_files(paths):
    """解析が終わった一時画像を削除する（失敗しても処理は止めない）。"""
    for path in paths:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError as e:
                print(f"temp file cleanup failed for {path}: {e}")


@app.post("/ocr")
async def ocr_image(file: UploadFile = File(...)):
    image_path = None
    try:
        os.makedirs(TEMP_DIR, exist_ok=True)

        image_path = os.path.join(TEMP_DIR, unique_filename(file.filename))

        with open(image_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        texts = extract_text_from_image(image_path)
        candidates = extract_model_candidates(texts)

        return {
            "texts": texts,
            "candidates": [
                {
                    "model_number": candidate,
                    "score": score
                }
                for candidate, score in candidates
            ]
        }

    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
    finally:
        remove_temp_files([image_path])
    
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


@app.post("/similar-search")
async def similar_search(
    file: Optional[UploadFile] = File(None),
    files: Optional[List[UploadFile]] = File(None),
    top_k: int = 5,
):
    temp_paths: List[str] = []
    try:
        upload_files: List[UploadFile] = []

        if files:
            upload_files.extend(files)

        if file:
            upload_files.append(file)

        if not upload_files:
            raise HTTPException(
                status_code=400,
                detail="画像ファイルが必要です",
            )

        os.makedirs(TEMP_DIR, exist_ok=True)

        query_embeddings = []
        all_texts = []

        for index, upload_file in enumerate(upload_files):
            image_path = os.path.join(
                TEMP_DIR,
                unique_filename(
                    upload_file.filename or f"query_{index}.jpg",
                    prefix=f"{index}_",
                ),
            )
            temp_paths.append(image_path)

            with open(image_path, "wb") as buffer:
                shutil.copyfileobj(upload_file.file, buffer)

            try:
                texts = extract_text_from_image(image_path)
                all_texts.extend(texts)
            except Exception as ocr_error:
                print(f"OCR skipped for {image_path}: {ocr_error}")

            query_embeddings.append(
                normalize_embedding_vector(get_image_embedding(image_path))
            )

        ocr_candidates = extract_model_candidates(all_texts)
        detected_maker = detect_maker_from_text(all_texts)
        product_name_hints = extract_product_name_hints(all_texts)

        all_products = fetch_all_products()
        similar_model_results = find_similar_model_numbers(
            ocr_candidates,
            all_products,
        )

        image_results = compute_similar_results(
            query_embeddings,
            top_k=max(top_k * 2, 10),
        )

        results = merge_similar_search_results(
            image_results,
            ocr_candidates,
            detected_maker,
            similar_model_results,
            all_products,
            product_name_hints,
            top_k=top_k,
        )

        return {
            "results": results,
            "detected_maker": detected_maker,
            "ocr_candidates": [
                {"model_number": candidate, "score": score}
                for candidate, score in ocr_candidates[:8]
            ],
            "product_name_hints": product_name_hints,
            "min_similarity": MIN_SIMILARITY,
            "query_image_count": len(upload_files),
        }

    except HTTPException:
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
    finally:
        remove_temp_files(temp_paths)
    
@app.post("/match-products")
def match_products(candidates: list[str]):
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

    rows = cur.fetchall()
    conn.close()

    results = []

    for candidate in candidates:
        candidate_upper = candidate.upper()

        for row in rows:
            row_dict = dict(row)
            db_model = str(row_dict["model_number"]).upper()

            similarity = SequenceMatcher(
                None,
                candidate_upper,
                db_model
            ).ratio()

            if candidate_upper == db_model:
                score = 100
            else:
                similarity = SequenceMatcher(
                    None,
                    candidate_upper,
                    db_model,
                ).ratio()

                if similarity < 0.85:
                    continue

                score = round(similarity * 100, 1)

            results.append({
                "ocr_candidate": candidate,
                "product": row_dict,
                "score": score
            })

    results = sorted(
        results,
        key=lambda x: x["score"],
        reverse=True
    )

    return {
        "results": results[:5]
    }

@app.post("/autocomplete-product")
def autocomplete_product(payload: ProductAutocompleteRequest):
    """
    型番・商品ページURLから登録フォームを自動補完する。
    Webページのメタ情報・JSON-LD・DB類似・型番ルールを組み合わせる。
    """
    model_number = (payload.model_number or "").strip()
    url = (payload.url or "").strip()

    if not model_number and not url:
        raise HTTPException(
            status_code=400,
            detail="model_number または url のいずれかを指定してください",
        )

    try:
        products = fetch_all_products()
        suggestion = product_ai.build_product_autocomplete(
            model_number=model_number,
            url=url,
            products=products,
        )
        return suggestion
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/suggest-product-name")
def suggest_product_name(
    model_number: str = Body(...)
):
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
            memo,
            tags
        FROM products
    """)

    rows = cur.fetchall()
    conn.close()

    best_match = None
    best_score = 0

    target = model_number.upper()

    for row in rows:
        row_dict = dict(row)

        db_model = str(row_dict["model_number"]).upper()

        similarity = SequenceMatcher(
            None,
            target,
            db_model
        ).ratio()

        score = similarity * 100

        # メーカー接頭辞強化
        if target[:3] == db_model[:3]:
            score += 10

        if score > best_score:
            best_score = score
            best_match = row_dict

    if best_match is None:
        return {
            "suggested_product_name": "",
            "suggested_category": "",
            "suggested_tags": "",
            "score": 0
        }

    return {
        "suggested_product_name": best_match["product_name"],
        "suggested_category": best_match["category"],
        "suggested_tags": best_match["tags"],
        "score": best_score,
        "matched_model_number": best_match["model_number"]
    }

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

@app.get("/ai-search")
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


@app.post("/embeddings/rebuild-text")
def rebuild_text_embeddings():
    try:
        updated = rebuild_missing_product_text_embeddings()
        return {"updated": updated}
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


CODE_QUERY_KEYS = [
    "model",
    "model_number",
    "modelno",
    "product_code",
    "code",
    "jan",
    "barcode",
    "sku",
    "品番",
    "型番",
]


def parse_scanned_code(raw: str):
    raw = (raw or "").strip()
    if not raw:
        return {"raw": "", "terms": [], "primary": ""}

    terms = []

    if raw.startswith("{") or raw.startswith("["):
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                for key in [
                    "model_number",
                    "model",
                    "product_code",
                    "jan",
                    "barcode",
                    "code",
                    "品番",
                    "型番",
                ]:
                    value = data.get(key)
                    if value:
                        terms.append(str(value).strip())
        except json.JSONDecodeError:
            pass

    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlparse(raw)
        query = parse_qs(parsed.query)

        for key in CODE_QUERY_KEYS:
            if key in query:
                terms.extend([value.strip() for value in query[key] if value.strip()])

        for part in parsed.path.split("/"):
            part = unquote(part).strip()
            if len(part) >= 4:
                terms.append(part)

    if not terms:
        terms.append(raw)
    elif raw not in terms:
        terms.insert(0, raw)

    seen = set()
    unique_terms = []
    for term in terms:
        key = term.lower()
        if not term or key in seen:
            continue
        seen.add(key)
        unique_terms.append(term)

    return {
        "raw": raw,
        "terms": unique_terms,
        "primary": unique_terms[0] if unique_terms else "",
    }


def compact_code(value: str):
    return re.sub(r"[\s\-_./]", "", str(value or "")).upper()


def search_products_by_barcode(code: str):
    parsed = parse_scanned_code(code)
    terms = parsed["terms"]

    if not terms:
        return {"results": [], "parsed": parsed}

    all_products = fetch_all_products()
    results = {}

    for product in all_products:
        score = 0.0
        match_types = []
        matched_term = ""

        db_model = str(product.get("model_number") or "")
        db_maker = str(product.get("maker") or "")
        db_name = str(product.get("product_name") or "")
        db_tags = str(product.get("tags") or "")
        db_memo = str(product.get("memo") or "")

        combined_upper = " ".join(
            [db_model, db_maker, db_name, db_tags, db_memo]
        ).upper()
        model_compact = compact_code(db_model)

        for term in terms:
            term_upper = term.upper()
            term_compact = compact_code(term)

            if term_upper == db_model.upper() or term_compact == model_compact:
                score = max(score, 100)
                match_types.append("model_exact")
                matched_term = term
                continue

            if term_compact and term_compact in compact_code(combined_upper):
                score = max(score, 90)
                match_types.append("contains")
                matched_term = term
                continue

            if term_upper in combined_upper:
                score = max(score, 85)
                match_types.append("contains")
                matched_term = term
                continue

            model_similarity = SequenceMatcher(
                None,
                term_upper,
                db_model.upper(),
            ).ratio()

            if model_similarity >= 0.82:
                score = max(score, model_similarity * 92)
                match_types.append("model_fuzzy")
                matched_term = term

        if score >= 55:
            product_id = product["id"]
            existing = results.get(product_id)

            if existing is None or score > existing["score"]:
                results[product_id] = {
                    "product": product_row_to_result(product),
                    "score": round(score, 1),
                    "match_types": list(dict.fromkeys(match_types)),
                    "matched_term": matched_term,
                }

    sorted_results = sorted(
        results.values(),
        key=lambda x: x["score"],
        reverse=True,
    )[:10]

    return {
        "results": sorted_results,
        "parsed": parsed,
    }


@app.get("/barcode-search")
def barcode_search(code: str = ""):
    if not code.strip():
        raise HTTPException(status_code=400, detail="code が必要です")

    try:
        return search_products_by_barcode(code)
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/field-suggestions")
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


@app.get("/search-suggestions")
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