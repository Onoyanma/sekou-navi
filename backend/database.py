"""データベースとファイル保存先の設定・初期化。

保存先は環境変数で変更できる（未設定ならリポジトリ直下を使う）。
- SEKOU_DB_PATH    : SQLite ファイルのパス（既定: <repo>/products.db）
- SEKOU_IMAGE_DIR  : 商品画像の保存先（既定: <repo>/images）
- SEKOU_TEMP_DIR   : OCR・類似検索用の一時画像の保存先（既定: <repo>/temp_images）
"""

from __future__ import annotations

import os
import re
import sqlite3
import uuid

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))

DB_PATH = os.environ.get("SEKOU_DB_PATH", os.path.join(PROJECT_ROOT, "products.db"))
IMAGE_DIR = os.environ.get("SEKOU_IMAGE_DIR", os.path.join(PROJECT_ROOT, "images"))
TEMP_DIR = os.environ.get("SEKOU_TEMP_DIR", os.path.join(PROJECT_ROOT, "temp_images"))

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        maker TEXT,
        product_name TEXT,
        model_number TEXT,
        category TEXT,
        image_path TEXT,
        manual_url TEXT,
        install_url TEXT,
        official_url TEXT,
        memo TEXT,
        created_at TEXT,
        tags TEXT,
        image_embedding BLOB,
        text_embedding BLOB
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS product_images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER,
        image_path TEXT,
        image_type TEXT,
        image_embedding BLOB,
        created_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ocr_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        image_path TEXT,
        detected_maker TEXT,
        candidates TEXT,
        created_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ocr_texts TEXT,
        maker TEXT,
        suggested_category TEXT,
        final_category TEXT,
        suggested_tags TEXT,
        final_tags TEXT,
        created_at TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_product_images_product_id ON product_images(product_id)",
]

# 旧バージョンの DB に後から追加された列（既存 DB を壊さずに追加する）
PRODUCT_EXTRA_COLUMNS = {
    "tags": "TEXT",
    "image_embedding": "BLOB",
    "text_embedding": "BLOB",
}


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str | None = None) -> None:
    """テーブルが無ければ作成し、足りない列を追加する。何度呼んでも安全。"""
    path = db_path or DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    conn = sqlite3.connect(path)
    try:
        cur = conn.cursor()
        for statement in SCHEMA:
            cur.execute(statement)

        cur.execute("PRAGMA table_info(products)")
        existing = {row[1] for row in cur.fetchall()}
        for column, column_type in PRODUCT_EXTRA_COLUMNS.items():
            if column not in existing:
                cur.execute(f"ALTER TABLE products ADD COLUMN {column} {column_type}")

        conn.commit()
    finally:
        conn.close()


def ensure_storage_dirs() -> None:
    os.makedirs(IMAGE_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)


_UNSAFE_CHARS = re.compile(r"[^0-9A-Za-z._\-぀-ヿ㐀-鿿]")


def safe_filename(filename: str | None, default: str = "upload.jpg") -> str:
    """アップロードされたファイル名から、保存しても安全な名前を作る。

    パス区切り（../ など）を取り除き、記号や空白を _ に置き換える。
    """
    name = os.path.basename((filename or "").replace("\\", "/")).strip()
    name = _UNSAFE_CHARS.sub("_", name).lstrip(".")
    if not name:
        name = default
    if len(name) > 120:
        stem, ext = os.path.splitext(name)
        name = stem[: 120 - len(ext)] + ext
    return name


def unique_filename(filename: str | None, prefix: str = "") -> str:
    """同名ファイルの上書きを防ぐため、短いランダム文字列を付けた名前を返す。"""
    return f"{prefix}{uuid.uuid4().hex[:8]}_{safe_filename(filename)}"
