"""画像・文章の埋め込みベクトル（CLIP / SentenceTransformers）の計算と保存。"""

import os
import pickle
import sqlite3

import numpy as np
from PIL import Image
from sentence_transformers import SentenceTransformer

from database import BASE_DIR, DB_PATH as DB_NAME, IMAGE_DIR


_image_model = None

text_model = None
TEXT_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


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
