import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import os
from PIL import Image, UnidentifiedImageError
import easyocr
import re
import urllib.parse
from PIL import Image, ImageEnhance, ImageFilter
from sentence_transformers import SentenceTransformer
from PIL import Image
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import pickle
import streamlit.components.v1 as components
import faiss
from difflib import SequenceMatcher
import requests
from bs4 import BeautifulSoup

DB_NAME = "products.db"
IMAGE_DIR = "images"


def show_image_safely(image_path, width=220):
    if not image_path:
        st.write("画像なし")
        return

    if not os.path.exists(image_path):
        st.write("画像ファイルが見つかりません")
        return

    try:
        image = Image.open(image_path)
        st.image(image, width=width)

    except UnidentifiedImageError:
        st.write("画像として読み込めません")

@st.cache_resource
def load_ocr_reader():
    return easyocr.Reader(["en"], gpu=False)

@st.cache_resource
def load_image_model():
    return SentenceTransformer("clip-ViT-B-32")

def preprocess_image_for_ocr(image_path):
    image = Image.open(image_path)

    # グレースケール化
    image = image.convert("L")

    # コントラスト強調
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(2.0)

    # シャープ化
    image = image.filter(ImageFilter.SHARPEN)

    # サイズ拡大
    width, height = image.size
    image = image.resize((width * 2, height * 2))

    processed_path = image_path.replace(".", "_processed.")

    image.save(processed_path)

    return processed_path

def extract_text_from_image(image_path):
    processed_path = preprocess_image_for_ocr(image_path)

    reader = load_ocr_reader()

    results = reader.readtext(
        processed_path,
        detail=0
    )

    return results

def get_image_embedding(image_path):
    model = load_image_model()

    image = Image.open(image_path).convert("RGB")

    embedding = model.encode(image)

    return embedding

def embedding_to_blob(embedding):
    return pickle.dumps(embedding)


def blob_to_embedding(blob):
    if blob is None:
        return None

    return pickle.loads(blob)

@st.cache_resource
def build_faiss_index():
    conn = sqlite3.connect(DB_NAME)

    image_df = pd.read_sql_query("""
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
            products.tags
        FROM product_images
        JOIN products
        ON product_images.product_id = products.id
        WHERE product_images.image_embedding IS NOT NULL
    """, conn)

    conn.close()

    if image_df.empty:
        return None, []

    embeddings = []
    rows = []

    for _, row in image_df.iterrows():
        embedding = blob_to_embedding(row["image_embedding"])

        if embedding is None:
            continue

        embeddings.append(embedding.astype("float32"))
        rows.append(row)

    if not embeddings:
        return None, []

    embedding_matrix = np.vstack(embeddings).astype("float32")

    faiss.normalize_L2(embedding_matrix)

    dimension = embedding_matrix.shape[1]

    index = faiss.IndexFlatIP(dimension)
    index.add(embedding_matrix)

    return index, rows

def search_similar_images_fast(query_image_path, top_k=5):
    query_embedding = get_image_embedding(query_image_path)

    conn = sqlite3.connect(DB_NAME)

    image_df = pd.read_sql_query("""
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
            products.tags
        FROM product_images
        JOIN products
        ON product_images.product_id = products.id
    """, conn)

    conn.close()

    if image_df.empty:
        return []

    best_results = {}

    for _, row in image_df.iterrows():
        stored_embedding = blob_to_embedding(row["image_embedding"])

        if stored_embedding is None:
            continue

        similarity = cosine_similarity(
            [query_embedding],
            [stored_embedding]
        )[0][0]

        product_id = row["product_id"]

        if product_id not in best_results:
            best_results[product_id] = {
                "row": row,
                "similarity": similarity
            }
        else:
            if similarity > best_results[product_id]["similarity"]:
                best_results[product_id] = {
                    "row": row,
                    "similarity": similarity
                }

    results = list(best_results.values())

    results = sorted(
        results,
        key=lambda x: x["similarity"],
        reverse=True
    )

    return results[:top_k]

def search_similar_images_fast(query_image_path, top_k=5):
    query_embedding = get_image_embedding(query_image_path).astype("float32")

    index, rows = build_faiss_index()

    if index is None or not rows:
        return []

    query_matrix = np.array([query_embedding]).astype("float32")
    faiss.normalize_L2(query_matrix)

    search_k = min(top_k * 5, len(rows))

    scores, indices = index.search(query_matrix, search_k)

    best_results = {}

    for score, idx in zip(scores[0], indices[0]):
        if idx == -1:
            continue

        row = rows[idx]
        product_id = row["product_id"]

        if product_id not in best_results:
            best_results[product_id] = {
                "row": row,
                "similarity": float(score)
            }
        else:
            if float(score) > best_results[product_id]["similarity"]:
                best_results[product_id] = {
                    "row": row,
                    "similarity": float(score)
                }

    results = list(best_results.values())

    results = sorted(
        results,
        key=lambda x: x["similarity"],
        reverse=True
    )

    return results[:top_k]

def generate_missing_embeddings():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM products", conn)

    updated_count = 0

    for _, row in df.iterrows():
        product_id = row["id"]
        image_path = row["image_path"]
        image_embedding = row["image_embedding"]

        if image_embedding is not None:
            continue

        if not image_path:
            continue

        if not os.path.exists(image_path):
            continue

        try:
            embedding = get_image_embedding(image_path)
            embedding_blob = embedding_to_blob(embedding)

            cur = conn.cursor()
            cur.execute(
                "UPDATE products SET image_embedding = ? WHERE id = ?",
                (embedding_blob, product_id)
            )

            updated_count += 1

        except Exception:
            continue

    conn.commit()
    conn.close()

    return updated_count

def calculate_combined_candidates(ocr_candidates, detected_maker, similar_results):
    combined_results = []

    for result in similar_results:
        row = result["row"]
        similarity = result["similarity"]

        score = 0

        image_type = row.get("image_type", "その他")

        image_type_weights = {
            "型番ラベル": 1.5,
            "全体写真": 1.2,
            "部品アップ": 1.1,
            "施工例": 0.7,
            "その他": 1.0
        }

        weight = image_type_weights.get(image_type, 1.0)

        score += similarity * 50 * weight

        # メーカー一致：+20点
        if detected_maker and row["maker"]:
            if detected_maker.lower() in row["maker"].lower():
                score += 20

        # OCR型番一致：最大30点
        for candidate, ocr_score in ocr_candidates:
            if candidate.lower() in row["model_number"].lower():
                score += 30
            elif row["model_number"].lower() in candidate.lower():
                score += 20

        combined_results.append({
            "row": row,
            "combined_score": score,
            "similarity": similarity
        })

    combined_results = sorted(
        combined_results,
        key=lambda x: x["combined_score"],
        reverse=True
    )

    return combined_results

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

            # 小文字を大文字に統一
            normalized_match = upper_match

            variants = generate_ocr_variants(normalized_match)

            for variant in variants:
                variant_score = score

                if variant != normalized_match:
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

def find_similar_model_numbers(ocr_candidates, threshold=0.75):
    df = get_all_products()

    if df.empty:
        return []

    results = []

    db_models = df["model_number"].dropna().unique()

    for candidate, ocr_score in ocr_candidates:
        candidate_upper = candidate.upper()

        for db_model in db_models:
            db_model_upper = str(db_model).upper()

            similarity = SequenceMatcher(
                None,
                candidate_upper,
                db_model_upper
            ).ratio()

            if similarity >= threshold:
                results.append({
                    "ocr_candidate": candidate,
                    "db_model": db_model,
                    "similarity": similarity,
                    "ocr_score": ocr_score
                })

    results = sorted(
        results,
        key=lambda x: (x["similarity"], x["ocr_score"]),
        reverse=True
    )

    return results[:5]

def decide_final_model_candidates(
    ocr_candidates,
    detected_maker="",
    similar_results=None
):
    if similar_results is None:
        similar_results = []

    final_scores = {}

    # 1. OCR候補を加点
    for candidate, score in ocr_candidates:
        final_scores[candidate] = final_scores.get(candidate, 0) + score

    # 2. 既存DBの近い型番を加点
    similar_model_results = find_similar_model_numbers(
        ocr_candidates,
        threshold=0.7
    )

    for result in similar_model_results:
        db_model = result["db_model"]
        similarity = result["similarity"]
        ocr_score = result["ocr_score"]

        score = similarity * 100 + ocr_score * 0.3

        final_scores[db_model] = final_scores.get(db_model, 0) + score

    # 3. 類似画像の商品型番を加点
    for result in similar_results:
        row = result["row"]
        similarity = result["similarity"]

        model_number = row["model_number"]

        score = similarity * 80

        if detected_maker and row["maker"]:
            if detected_maker.lower() in row["maker"].lower():
                score += 20

        final_scores[model_number] = final_scores.get(model_number, 0) + score

    final_candidates = sorted(
        final_scores.items(),
        key=lambda x: x[1],
        reverse=True
    )

    return final_candidates[:5]

def find_existing_product_candidates(
    model_number="",
    maker="",
    uploaded_image_path="",
    threshold=0.75
):
    df = get_all_products()

    if df.empty:
        return []

    candidates = []

    # 1. 型番の近さで候補
    for _, row in df.iterrows():
        score = 0

        db_model = str(row["model_number"]).upper()
        input_model = str(model_number).upper()

        if input_model and db_model:
            similarity = SequenceMatcher(
                None,
                input_model,
                db_model
            ).ratio()

            if similarity >= threshold:
                score += similarity * 70

        if maker and row["maker"]:
            if maker.lower() in str(row["maker"]).lower():
                score += 20

        if score > 0:
            candidates.append({
                "row": row,
                "score": score
            })

    # 2. 画像類似でも候補
    if uploaded_image_path:
        similar_results = search_similar_images_fast(
            uploaded_image_path,
            top_k=5
        )

        for result in similar_results:
            row = result["row"]
            similarity = result["similarity"]

            score = similarity * 80

            if maker and row["maker"]:
                if maker.lower() in str(row["maker"]).lower():
                    score += 20

            candidates.append({
                "row": row,
                "score": score
            })

    # 3. 同じ商品が複数回出たら一番高いスコアだけ残す
    best = {}

    for item in candidates:
        row = item["row"]
        product_id = row["id"]

        if product_id not in best:
            best[product_id] = item
        else:
            if item["score"] > best[product_id]["score"]:
                best[product_id] = item

    results = list(best.values())

    results = sorted(
        results,
        key=lambda x: x["score"],
        reverse=True
    )

    return results[:3]

def detect_maker_from_text(text_list):
    joined_text = " ".join(text_list).upper()

    maker_aliases = {
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
        "ノーリツ": ["NORITZ", "ノーリツ"]
    }

    for maker, aliases in maker_aliases.items():
        for alias in aliases:
            if alias.upper() in joined_text:
                return maker

    return ""

def create_google_search_url(query):
    encoded_query = urllib.parse.quote(query)
    return f"https://www.google.com/search?q={encoded_query}"


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
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
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ocr_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_path TEXT,
            detected_maker TEXT,
            candidates TEXT,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS product_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            image_path TEXT,
            image_type TEXT,
            image_embedding BLOB,
            created_at TEXT
        )
    """)

    cur.execute("""
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
    """)

    # 既存DBに tags 列がなければ追加する
    cur.execute("PRAGMA table_info(products)")
    columns = [column[1] for column in cur.fetchall()]

    if "tags" not in columns:
        cur.execute("ALTER TABLE products ADD COLUMN tags TEXT")

    if "image_embedding" not in columns:
        cur.execute("ALTER TABLE products ADD COLUMN image_embedding BLOB")

    conn.commit()
    conn.close()


def add_product(
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
    image_embedding
):
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
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
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()

    product_id = cur.lastrowid

    conn.close()

    return product_id

def update_product(
    product_id,
    maker,
    product_name,
    model_number,
    category,
    image_path,
    manual_url,
    install_url,
    official_url,
    memo,
    tags
):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        UPDATE products
        SET
            maker = ?,
            product_name = ?,
            model_number = ?,
            category = ?,
            image_path = ?,
            manual_url = ?,
            install_url = ?,
            official_url = ?,
            memo = ?,
            tags = ?
        WHERE id = ?
    """, (
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
        product_id
    ))

    conn.commit()
    conn.close()

def update_install_url(product_id, install_url):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        UPDATE products
        SET install_url = ?
        WHERE id = ?
    """, (
        install_url,
        product_id
    ))

    conn.commit()
    conn.close()

def delete_product(product_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    # 画像パス取得
    cur.execute(
        "SELECT image_path FROM products WHERE id = ?",
        (product_id,)
    )

    row = cur.fetchone()

    if row:
        image_path = row[0]

        # 画像ファイル削除
        if image_path and os.path.exists(image_path):
            os.remove(image_path)

    # DB削除
    cur.execute(
        "DELETE FROM products WHERE id = ?",
        (product_id,)
    )

    conn.commit()
    conn.close()

def search_products(keyword="", maker="", product_name="", model_number="", category="すべて"):
    conn = sqlite3.connect(DB_NAME)

    query = "SELECT * FROM products WHERE 1=1"
    params = []

    if keyword:
        query += """
        AND (
            maker LIKE ?
            OR product_name LIKE ?
            OR model_number LIKE ?
            OR category LIKE ?
            OR memo LIKE ?
            OR tags LIKE ?
        )
        """
        for _ in range(6):
            params.append(f"%{keyword}%")

    if maker:
        query += " AND maker LIKE ?"
        params.append(f"%{maker}%")

    if product_name:
        query += """
        AND (
            product_name LIKE ?
            OR memo LIKE ?
            OR tags LIKE ?
        )
        """
        params.append(f"%{product_name}%")
        params.append(f"%{product_name}%")
        params.append(f"%{product_name}%")

    if model_number:
        query += " AND model_number LIKE ?"
        params.append(f"%{model_number}%")

    if category != "すべて":
        query += " AND category = ?"
        params.append(category)

    query += " ORDER BY created_at DESC"

    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    return df

def get_search_suggestions(keyword):
    if not keyword:
        return []

    conn = sqlite3.connect(DB_NAME)

    query = """
    SELECT DISTINCT value FROM (
        SELECT maker AS value FROM products
        UNION
        SELECT product_name AS value FROM products
        UNION
        SELECT model_number AS value FROM products
        UNION
        SELECT tags AS value FROM products
    )
    WHERE value LIKE ?
    LIMIT 10
    """

    df = pd.read_sql_query(
        query,
        conn,
        params=(f"%{keyword}%",)
    )

    conn.close()

    suggestions = df["value"].dropna().tolist()

    return suggestions

def get_all_products(sort_by="created_at"):
    conn = sqlite3.connect(DB_NAME)

    allowed_columns = [
        "created_at",
        "maker",
        "product_name",
        "model_number"
    ]

    if sort_by not in allowed_columns:
        sort_by = "created_at"

    query = f"""
        SELECT *
        FROM products
        ORDER BY {sort_by} COLLATE NOCASE ASC
    """

    if sort_by == "created_at":
        query = """
            SELECT *
            FROM products
            ORDER BY created_at DESC
        """

    df = pd.read_sql_query(query, conn)

    conn.close()

    return df

def is_duplicate_model(model_number):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute(
        "SELECT COUNT(*) FROM products WHERE model_number = ?",
        (model_number,)
    )

    count = cur.fetchone()[0]

    conn.close()

    return count > 0

def get_product_by_model_number(model_number):
    conn = sqlite3.connect(DB_NAME)

    query = """
        SELECT *
        FROM products
        WHERE model_number = ?
        LIMIT 1
    """

    df = pd.read_sql_query(query, conn, params=(model_number,))
    conn.close()

    if df.empty:
        return None

    return df.iloc[0]

def add_ocr_history(image_path, detected_maker, ocr_candidates):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    candidates_text = ",".join([
        f"{candidate}:{score}"
        for candidate, score in ocr_candidates
    ])

    cur.execute("""
        INSERT INTO ocr_history
        (image_path, detected_maker, candidates, created_at)
        VALUES (?, ?, ?, ?)
    """, (
        image_path,
        detected_maker,
        candidates_text,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()


def get_ocr_history():
    conn = sqlite3.connect(DB_NAME)

    df = pd.read_sql_query(
        "SELECT * FROM ocr_history ORDER BY created_at DESC",
        conn
    )

    conn.close()
    return df

def save_uploaded_image(uploaded_image):
    if uploaded_image is None:
        return ""

    os.makedirs(IMAGE_DIR, exist_ok=True)

    file_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uploaded_image.name}"
    image_path = os.path.join(IMAGE_DIR, file_name)

    with open(image_path, "wb") as f:
        f.write(uploaded_image.getbuffer())

    return image_path

def save_uploaded_images(uploaded_images):
    if not uploaded_images:
        return ""

    image_paths = []

    for uploaded_image in uploaded_images:
        image_path = save_uploaded_image(uploaded_image)

        if image_path:
            image_paths.append(image_path)

    return ",".join(image_paths)

def run_ai_search_from_image(image_path):
    texts = extract_text_from_image(image_path)
    ocr_candidates = extract_model_candidates(texts)
    detected_maker = detect_maker_from_text(texts)

    similar_results = search_similar_images_fast(image_path, top_k=5)

    combined_results = calculate_combined_candidates(
        ocr_candidates,
        detected_maker,
        similar_results
    )

    return texts, ocr_candidates, detected_maker, similar_results, combined_results

def show_pdf_in_app(pdf_url, height=700):
    if not pdf_url:
        st.info("PDF URLが登録されていません。")
        return

    components.iframe(
        pdf_url,
        height=height,
        scrolling=True
    )

def show_product_images(image_paths_text, width=220):
    if not image_paths_text:
        st.write("画像なし")
        return

    image_paths = str(image_paths_text).split(",")

    for image_path in image_paths:
        image_path = image_path.strip()

        if image_path:
            show_image_safely(image_path, width=width)

def show_first_product_image(product_id, fallback_image_path="", width=220):
    image_df = get_product_images(product_id)

    if not image_df.empty:
        first_image = image_df.iloc[0]
        show_image_safely(first_image["image_path"], width=width)
        return

    if fallback_image_path:
        first_path = str(fallback_image_path).split(",")[0]
        show_image_safely(first_path, width=width)
    else:
        st.write("画像なし")

def add_product_image(product_id, image_path, image_type="その他"):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    image_embedding = None

    if image_path:
        embedding = get_image_embedding(image_path)
        image_embedding = embedding_to_blob(embedding)

    cur.execute("""
        INSERT INTO product_images
        (product_id, image_path, image_type, image_embedding, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        product_id,
        image_path,
        image_type,
        image_embedding,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()

    product_id = cur.lastrowid

    conn.close()

    return product_id

def get_product_images(product_id):
    conn = sqlite3.connect(DB_NAME)

    df = pd.read_sql_query(
        "SELECT * FROM product_images WHERE product_id = ? ORDER BY created_at DESC",
        conn,
        params=(product_id,)
    )

    conn.close()
    return df

def update_product_image_type(image_id, image_type):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        UPDATE product_images
        SET image_type = ?
        WHERE id = ?
    """, (
        image_type,
        image_id
    ))

    conn.commit()
    conn.close()


def delete_product_image(image_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute(
        "SELECT image_path FROM product_images WHERE id = ?",
        (image_id,)
    )

    row = cur.fetchone()

    if row:
        image_path = row[0]

        if image_path and os.path.exists(image_path):
            os.remove(image_path)

    cur.execute(
        "DELETE FROM product_images WHERE id = ?",
        (image_id,)
    )

    conn.commit()
    conn.close()


def add_uploaded_images_to_product(product_id, uploaded_images, image_type="その他"):
    if not uploaded_images:
        return 0

    count = 0

    for uploaded_image in uploaded_images:
        saved_path = save_uploaded_image(uploaded_image)

        if saved_path:
            add_product_image(
                product_id=product_id,
                image_path=saved_path,
                image_type=image_type
            )
            count += 1

    return count

def migrate_existing_images_to_product_images():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT id, image_path FROM products", conn)

    migrated_count = 0

    for _, row in df.iterrows():
        product_id = row["id"]
        image_paths_text = row["image_path"]

        if not image_paths_text:
            continue

        image_paths = str(image_paths_text).split(",")

        for image_path in image_paths:
            image_path = image_path.strip()

            if not image_path:
                continue

            if not os.path.exists(image_path):
                continue

            cur = conn.cursor()

            cur.execute(
                """
                SELECT COUNT(*)
                FROM product_images
                WHERE product_id = ? AND image_path = ?
                """,
                (product_id, image_path)
            )

            exists_count = cur.fetchone()[0]

            if exists_count > 0:
                continue

            image_embedding = None

            try:
                embedding = get_image_embedding(image_path)
                image_embedding = embedding_to_blob(embedding)
            except Exception:
                image_embedding = None

            cur.execute(
                """
                INSERT INTO product_images
                (product_id, image_path, image_type, image_embedding, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    product_id,
                    image_path,
                    "その他",
                    image_embedding,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
            )

            migrated_count += 1

    conn.commit()
    conn.close()

    return migrated_count

def suggest_tags(maker="", category="", memo="", ocr_texts=None):
    if ocr_texts is None:
        ocr_texts = []

    text = " ".join([
        str(maker),
        str(category),
        str(memo),
        " ".join(ocr_texts)
    ]).upper()

    suggestions = set()

    if any(word in text for word in ["TOTO", "LIXIL", "INAX", "水", "トイレ", "洗面", "浴室", "キッチン"]):
        suggestions.add("水回り")

    if any(word in text for word in ["PANASONIC", "三菱", "電気", "換気", "スイッチ", "照明"]):
        suggestions.add("電気")

    if any(word in text for word in ["注意", "漏れ", "割れ", "破損", "ミス", "要確認"]):
        suggestions.add("注意必要")

    if any(word in text for word in ["新人", "簡単", "基本", "よく使う"]):
        suggestions.add("新人向け")

    if any(word in text for word in ["特殊", "専用", "別売", "工具"]):
        suggestions.add("特殊施工")

    feedback_tags = get_tags_from_feedback(
        maker=maker,
        ocr_texts=ocr_texts
    )

    for tag in feedback_tags:
        suggestions.add(tag)

    return [
        tag for tag in tag_options
        if tag in suggestions
    ]

def suggest_category(maker="", memo="", ocr_texts=None, image_types=None):
    if ocr_texts is None:
        ocr_texts = []

    if image_types is None:
        image_types = []

    text = " ".join([
        str(maker),
        str(memo),
        " ".join(ocr_texts),
        " ".join(image_types)
    ]).upper()

    category_scores = {
        "キッチン": 0,
        "トイレ": 0,
        "洗面台": 0,
        "浴室": 0,
        "建具": 0,
        "床材": 0,
        "壁材": 0,
        "サッシ": 0,
        "電気設備": 0,
        "換気扇": 0,
        "給排水部材": 0,
        "工具": 0,
        "その他": 0
    }

    rules = {
        "トイレ": ["トイレ", "便器", "便座", "ウォシュレット", "CS", "TCF", "DT-", "BC-"],
        "キッチン": ["キッチン", "シンク", "水栓", "蛇口", "TKS", "SF-", "BF-"],
        "洗面台": ["洗面", "洗面台", "化粧台", "TL", "LF-"],
        "浴室": ["浴室", "風呂", "バス", "シャワー", "TBV", "BF-"],
        "換気扇": ["換気", "FAN", "FY-", "VD-", "VENT"],
        "電気設備": ["スイッチ", "照明", "電気", "PANASONIC", "WT", "WTC", "WN"],
        "サッシ": ["サッシ", "YKK", "窓", "APW"],
        "建具": ["建具", "ドア", "扉", "DAIKEN"],
        "床材": ["床", "フローリング"],
        "壁材": ["壁", "クロス", "石膏ボード"],
        "給排水部材": ["給水", "排水", "パッキン", "止水", "継手"],
        "工具": ["工具", "ドライバー", "レンチ", "インパクト"]
    }

    for category, keywords in rules.items():
        for keyword in keywords:
            if keyword.upper() in text:
                category_scores[category] += 10

    if maker in ["TOTO", "LIXIL"]:
        category_scores["トイレ"] += 5
        category_scores["キッチン"] += 3
        category_scores["洗面台"] += 3
        category_scores["浴室"] += 3

    if maker == "Panasonic":
        category_scores["電気設備"] += 5
        category_scores["換気扇"] += 5

    if "型番ラベル" in image_types:
        category_scores["その他"] += 0

    feedback_category = get_category_from_feedback(
        maker=maker,
        ocr_texts=ocr_texts
    )

    if feedback_category:
        if feedback_category in category_scores:
            category_scores[feedback_category] += 25

    best_category = max(
        category_scores,
        key=category_scores.get
    )

    if category_scores[best_category] == 0:
        return "その他"

    return best_category

def suggest_image_type_from_texts(ocr_texts):
    if not ocr_texts:
        return "全体写真"

    candidates = extract_model_candidates(ocr_texts)

    if candidates:
        top_candidate, top_score = candidates[0]

        if top_score >= 80:
            return "型番ラベル"

    text_count = len(ocr_texts)

    if text_count >= 5:
        return "型番ラベル"

    return "全体写真"

def add_ai_feedback(
    ocr_texts,
    maker,
    suggested_category,
    final_category,
    suggested_tags,
    final_tags
):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    ocr_texts_text = ",".join(ocr_texts) if isinstance(ocr_texts, list) else str(ocr_texts)
    suggested_tags_text = ",".join(suggested_tags) if isinstance(suggested_tags, list) else str(suggested_tags)
    final_tags_text = ",".join(final_tags) if isinstance(final_tags, list) else str(final_tags)

    cur.execute("""
        INSERT INTO ai_feedback
        (
            ocr_texts,
            maker,
            suggested_category,
            final_category,
            suggested_tags,
            final_tags,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        ocr_texts_text,
        maker,
        suggested_category,
        final_category,
        suggested_tags_text,
        final_tags_text,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()

def get_category_from_feedback(maker="", ocr_texts=None):
    if ocr_texts is None:
        ocr_texts = []

    conn = sqlite3.connect(DB_NAME)

    df = pd.read_sql_query(
        "SELECT * FROM ai_feedback ORDER BY created_at DESC",
        conn
    )

    conn.close()

    if df.empty:
        return None

    current_text = " ".join(ocr_texts).upper()
    scores = {}

    for _, row in df.iterrows():
        score = 0

        past_maker = str(row["maker"])
        past_ocr_texts = str(row["ocr_texts"]).upper()
        past_category = row["final_category"]

        if maker and past_maker == maker:
            score += 30

        for word in current_text.split():
            if len(word) >= 4 and word in past_ocr_texts:
                score += 10

        if score > 0:
            scores[past_category] = scores.get(past_category, 0) + score

    if not scores:
        return None

    return max(scores, key=scores.get)

def get_tags_from_feedback(maker="", ocr_texts=None):
    if ocr_texts is None:
        ocr_texts = []

    conn = sqlite3.connect(DB_NAME)

    df = pd.read_sql_query(
        "SELECT * FROM ai_feedback ORDER BY created_at DESC",
        conn
    )

    conn.close()

    if df.empty:
        return []

    current_text = " ".join(ocr_texts).upper()
    tag_scores = {}

    for _, row in df.iterrows():
        score = 0

        past_maker = str(row["maker"])
        past_ocr_texts = str(row["ocr_texts"]).upper()
        past_tags = str(row["final_tags"]).split(",")

        if maker and past_maker == maker:
            score += 20

        for word in current_text.split():
            if len(word) >= 4 and word in past_ocr_texts:
                score += 10

        if score > 0:
            for tag in past_tags:
                tag = tag.strip()

                if tag:
                    tag_scores[tag] = tag_scores.get(tag, 0) + score

    if not tag_scores:
        return []

    sorted_tags = sorted(
        tag_scores.items(),
        key=lambda x: x[1],
        reverse=True
    )

    return [
        tag
        for tag, score in sorted_tags
        if tag in tag_options
    ][:3]

def find_pdf_candidates(maker, model_number, document_type="施工説明書", max_results=5):
    query = (
        f"{maker} {model_number} "
        f"施工説明書 取扱説明書 工事説明書 "
        f"取付説明書 PDF"
    )

    search_url = "https://duckduckgo.com/html/"
    params = {"q": query}

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    candidates = []

    try:
        response = requests.get(
            search_url,
            params=params,
            headers=headers,
            timeout=10
        )

        soup = BeautifulSoup(response.text, "html.parser")

        links = soup.select("a.result__a")

        for link in links:
            title = link.get_text(" ", strip=True)
            url = link.get("href")

            if not url:
                continue

            if model_number.upper() in text:
                text = f"{title} {url}".upper()

            if model_number.upper() in text:
                score += 50

            if maker.upper() in text:
                score += 20

            if "PDF" in text or ".PDF" in text:
                score += 20

            if document_type in title or document_type in url:
                score += 20

            if score > 0:
                candidates.append({
                    "title": title,
                    "url": url,
                    "score": score
                })

        candidates = sorted(
            candidates,
            key=lambda x: x["score"],
            reverse=True
        )

        return candidates[:max_results]

    except Exception as e:
        return []
    
def suggest_product_name_from_model(maker="", model_number="", category=""):
    model = model_number.upper()

    if model.startswith("TCF"):
        return "ウォシュレット"

    if model.startswith("CS") or model.startswith("BC"):
        return "便器"

    if model.startswith("TKS") or model.startswith("SF") or model.startswith("BF"):
        return "水栓"

    if model.startswith("FY") or model.startswith("VD"):
        return "換気扇"

    if model.startswith("WT") or model.startswith("WTC") or model.startswith("WN"):
        return "スイッチ"

    if model.startswith("RUF") or model.startswith("GT"):
        return "給湯器"

    if model.startswith("APW"):
        return "サッシ"

    if category:
        return category

    return "未登録"

init_db()

def seed_sample_products():
    sample_products = [
        {
            "maker": "TOTO",
            "product_name": "ウォシュレット",
            "model_number": "TCF8GM24",
            "category": "トイレ",
            "tags": "水回り,よく使う",
            "memo": "TOTOの温水洗浄便座系。型番確認用サンプル。"
        },
        {
            "maker": "TOTO",
            "product_name": "シングル混合水栓",
            "model_number": "TKS05305JA",
            "category": "キッチン",
            "tags": "水回り,よく使う",
            "memo": "キッチン水栓のサンプル。"
        },
        {
            "maker": "LIXIL",
            "product_name": "シャワートイレ",
            "model_number": "CW-KA31",
            "category": "トイレ",
            "tags": "水回り,注意必要",
            "memo": "LIXIL/INAX系トイレ部材サンプル。"
        },
        {
            "maker": "LIXIL",
            "product_name": "シングルレバー混合水栓",
            "model_number": "SF-WM420SYX",
            "category": "キッチン",
            "tags": "水回り",
            "memo": "キッチン水栓系サンプル。"
        },
        {
            "maker": "Panasonic",
            "product_name": "パイプファン",
            "model_number": "FY-08PD9",
            "category": "換気扇",
            "tags": "電気,換気,よく使う",
            "memo": "換気扇・電気設備系サンプル。"
        },
        {
            "maker": "Panasonic",
            "product_name": "埋込スイッチ",
            "model_number": "WT5001",
            "category": "電気設備",
            "tags": "電気,よく使う",
            "memo": "スイッチ系サンプル。"
        },
        {
            "maker": "YKK AP",
            "product_name": "APWシリーズ",
            "model_number": "APW330",
            "category": "サッシ",
            "tags": "サッシ,要確認",
            "memo": "サッシ系サンプル。"
        },
        {
            "maker": "DAIKEN",
            "product_name": "室内ドア",
            "model_number": "RIII",
            "category": "建具",
            "tags": "建具,要確認",
            "memo": "建具系サンプル。"
        },
        {
            "maker": "リンナイ",
            "product_name": "ガス給湯器",
            "model_number": "RUF-E2406SAW",
            "category": "給排水部材",
            "tags": "水回り,注意必要",
            "memo": "給湯器系サンプル。"
        },
        {
            "maker": "ノーリツ",
            "product_name": "ガスふろ給湯器",
            "model_number": "GT-C2462SAWX",
            "category": "給排水部材",
            "tags": "水回り,注意必要",
            "memo": "給湯器系サンプル。"
        },
    ]

    added_count = 0

    for item in sample_products:
        if is_duplicate_model(item["model_number"]):
            continue

        add_product(
            maker=item["maker"],
            product_name=item["product_name"],
            model_number=item["model_number"],
            category=item["category"],
            image_path="",
            manual_url="",
            install_url="",
            official_url="",
            memo=item["memo"],
            tags=item["tags"],
            image_embedding=None
        )

        added_count += 1

    return added_count

if "auto_embedding_done" not in st.session_state:
    generate_missing_embeddings()
    st.session_state["auto_embedding_done"] = True

st.set_page_config(
    page_title="施工ナビ",
    layout="wide"
)

st.title("施工ナビ")
st.caption("型番・カテゴリ・画像から取説や施工説明書にすぐ飛ぶアプリ")

main_menu = st.sidebar.radio(
    "メインメニュー",
    ["検索", "商品管理", "設定"]
)

if main_menu == "検索":
    menu = st.sidebar.radio(
        "検索メニュー",
        ["通常検索", "OCR履歴"]
    )

elif main_menu == "商品管理":
    menu = st.sidebar.radio(
        "商品管理メニュー",
        ["商品登録", "登録一覧", "商品編集"]
    )

elif main_menu == "設定":
    menu = st.sidebar.radio(
        "設定メニュー",
        ["施工説明書URL登録"]
    )

categories = [
    "すべて",
    "キッチン",
    "トイレ",
    "洗面台",
    "浴室",
    "建具",
    "床材",
    "壁材",
    "サッシ",
    "電気設備",
    "換気扇",
    "給排水部材",
    "工具",
    "その他"
]

tag_options = [
    "新人向け",
    "注意必要",
    "よく使う",
    "水回り",
    "電気",
    "サッシ",
    "建具",
    "工具必要",
    "特殊施工",
    "要確認",
    "施工ミス多い"
]

image_type_options = [
    "全体写真",
    "型番ラベル",
    "施工例",
    "梱包箱",
    "部品アップ",
    "その他"
]

maker_options = [
    "TOTO",
    "LIXIL",
    "Panasonic",
    "YKK AP",
    "DAIKEN",
    "クリナップ",
    "タカラスタンダード",
    "三菱電機",
    "日立",
    "リンナイ",
    "ノーリツ"
]


if menu == "通常検索":
    st.header("商品を探す")

    if "search_keyword" not in st.session_state:
        st.session_state["search_keyword"] = ""

    if "selected_suggestion" in st.session_state:
        st.session_state["search_keyword"] = st.session_state["selected_suggestion"]
        del st.session_state["selected_suggestion"]

    keyword = st.text_input(
        "フリーワード検索",
        key="search_keyword",
        placeholder="例：TOTO トイレ"
    )

    suggestions = get_search_suggestions(keyword)

    if suggestions:
        st.caption("検索候補")

        cols = st.columns(min(len(suggestions), 3))

        for idx, suggestion in enumerate(suggestions):
            with cols[idx % 3]:
                if st.button(
                    suggestion,
                    key=f"suggestion_{idx}"
                ):
                    st.session_state["selected_suggestion"] = suggestion
                    st.rerun()

    maker = st.text_input("メーカー名")
    product_name = st.text_input("商品名")
    model_number = st.text_input("型番")
    category = st.selectbox("カテゴリ", categories)

    uploaded_search_image = st.file_uploader(
        "画像検索（任意）",
        type=["jpg", "jpeg", "png"],
        key="normal_search_image"
    )

    if keyword or maker or product_name or model_number or category != "すべて" or uploaded_search_image:
        ai_results = []

        if uploaded_search_image is not None:
            os.makedirs("normal_search_images", exist_ok=True)

            search_image_path = os.path.join(
                "normal_search_images",
                f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uploaded_search_image.name}"
            )

            with open(search_image_path, "wb") as f:
                f.write(uploaded_search_image.getbuffer())

            st.subheader("画像検索結果")

            texts = extract_text_from_image(search_image_path)
            ocr_candidates = extract_model_candidates(texts)
            detected_maker = detect_maker_from_text(texts)

            similar_results = search_similar_images_fast(search_image_path, top_k=5)

            ai_results = calculate_combined_candidates(
                ocr_candidates,
                detected_maker,
                similar_results
            )

            if detected_maker:
                st.write(f"**検出メーカー**：{detected_maker}")

            high_score_candidates = [
                (candidate, score)
                for candidate, score in ocr_candidates
                if score >= 90
            ]

            if high_score_candidates:
                st.write("**型番候補**")
                for candidate, score in high_score_candidates:
                    st.write(f"- {candidate}（スコア：{score}）")
        df = search_products(
            keyword=keyword,
            maker=maker,
            product_name=product_name,
            model_number=model_number,
            category=category
        )

        if ai_results:
            similarity_map = {}

            for result in ai_results:
                ai_row = result["row"]
                combined_score = result["combined_score"]

                similarity_map[ai_row["id"]] = combined_score

            if not df.empty:
                df["ai_score"] = df["id"].map(similarity_map).fillna(0)

                df = df.sort_values(
                    by="ai_score",
                    ascending=False
                )

        normal_result_ids = set()

        if not df.empty:
            normal_result_ids = set(df["id"].tolist())

        if df.empty:
            st.warning("登録済み商品が見つかりませんでした。")
            
            search_words = []
            
            if maker:
                search_words.append(maker)

            if product_name:
                search_words.append(product_name)

            if model_number:
                search_words.append(model_number)

            search_words.append("施工説明書")

            google_query = " ".join(search_words)

            google_url = create_google_search_url(google_query)

            st.link_button(
                "Googleで施工説明書を検索",
                google_url
            )
        else:
            st.write(f"{len(df)}件見つかりました。")

            for _, row in df.iterrows():
                with st.container(border=True):
                    col_img, col_info = st.columns([1, 2])

                    with col_img:
                        show_product_images(row["image_path"], width=220)

                    with col_info:
                        st.write(f"**メーカー**：{row['maker']}")
                        st.write(f"**商品名**：{row['product_name']}")
                        st.write(f"**型番**：{row['model_number']}")

                        if "ai_score" in df.columns:
                            ai_score = row["ai_score"]

                            if ai_score >= 80:
                                st.success(f"AIスコア：{ai_score:.1f}")

                            elif ai_score >= 50:
                                st.warning(f"AIスコア：{ai_score:.1f}")

                            else:
                                st.error(f"AIスコア：{ai_score:.1f}")

                        st.write(f"**カテゴリ**：{row['category']}")
                        st.write(f"**タグ**：{row['tags']}")
                        st.write(f"**メモ**：{row['memo']}")
                        base_query = f"{row['maker']} {row['model_number']}"

                        st.link_button(
                            "Googleで施工説明書を検索",
                            create_google_search_url(f"{base_query} 施工説明書"),
                            key=f"search_google_install_{row['id']}"
                        )

                        if st.button(
                            "この商品を編集",
                            key=f"edit_from_search_{row['id']}"
                        ):
                            st.session_state["edit_product_id"] = row["id"]
                            st.success("商品編集メニューを開いてください。")

        if ai_results:
            st.subheader("AI補助候補")

            displayed_ai_count = 0

            for idx, result in enumerate(ai_results):
                ai_row = result["row"]

                if ai_row["id"] in normal_result_ids:
                    continue

                if displayed_ai_count >= 3:
                    break

                displayed_ai_count += 1
                combined_score = result["combined_score"]
                similarity = result["similarity"]

                with st.container(border=True):
                    col_img, col_info = st.columns([1, 2])

                    with col_img:
                        image_df = get_product_images(ai_row["id"])

                        if image_df.empty:
                            show_product_images(ai_row["image_path"], width=220)
                        else:
                            first_image = image_df.iloc[0]
                            show_image_safely(first_image["image_path"], width=220)

                    with col_info:
                        st.write(f"**メーカー**：{ai_row['maker']}")
                        st.write(f"**商品名**：{ai_row['product_name']}")
                        st.write(f"**型番**：{ai_row['model_number']}")
                        st.write(f"**類似度**：{similarity:.2f}")
                        st.write(f"**統合スコア**：{combined_score:.1f}")
                        st.write(f"**カテゴリ**：{ai_row['category']}")
                        st.write(f"**タグ**：{ai_row['tags']}")
                        st.write(f"**メモ**：{ai_row['memo']}")

                        base_query = f"{ai_row['maker']} {ai_row['model_number']}"

                        st.link_button(
                            "Googleで施工説明書を検索",
                            create_google_search_url(f"{base_query} 施工説明書"),
                            key=f"normal_search_ai_google_install_{ai_row['id']}_{idx}"
                        )

                        if st.button(
                            "この商品を編集",
                            key=f"normal_search_ai_edit_{ai_row['id']}_{idx}"
                        ):
                            st.session_state["edit_product_id"] = ai_row["id"]
                            st.success("商品編集メニューを開いてください。")
    else:
        st.info("メーカー名・商品名・型番のどれかを入力するか、カテゴリを選んでください。")

elif menu == "商品登録":
    st.header("商品を登録する")

    tab_easy, tab_detail = st.tabs([
        "AI簡単登録",
        "詳細登録"
    ])

    with tab_easy:
        st.subheader("AI簡単登録")

        easy_images = st.file_uploader(
            "商品画像をアップロード",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True,
            key="easy_register_images"
        )

        if "camera_mode" not in st.session_state:
            st.session_state["camera_mode"] = False

        if st.button("📷 カメラを起動"):
            st.session_state["camera_mode"] = True

        camera_image = None

        if st.session_state["camera_mode"]:
            camera_image = st.camera_input(
                "撮影してください",
                key="easy_camera_image"
            )

            if camera_image is not None:
                st.session_state["camera_mode"] = False

        easy_image_list = []

        if easy_image_list:
            easy_image_list.extend(easy_images)

        if camera_image is not None:
            easy_image_list.append(camera_image)

        if easy_image_list:
            st.write("アップロード画像")

            for img in easy_image_list:
                st.image(img, width=180)

            if st.button("AIで読み取る", key="easy_ai_read"):

                with st.spinner("AIが商品情報を解析しています..."):

                    os.makedirs("temp_images", exist_ok=True)

                    all_texts = []
                    last_temp_image_path = ""

                    for uploaded_image in easy_image_list:
                        temp_image_path = os.path.join(
                            "temp_images",
                            f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uploaded_image.name}"
                        )

                        with open(temp_image_path, "wb") as f:
                            f.write(uploaded_image.getbuffer())

                        texts = extract_text_from_image(temp_image_path)
                        all_texts.extend(texts)

                        last_temp_image_path = temp_image_path

                    ocr_candidates = extract_model_candidates(all_texts)
                    detected_maker = detect_maker_from_text(all_texts)

                    similar_results = search_similar_images_fast(
                        last_temp_image_path,
                        top_k=5
                    )

                    final_model_candidates = decide_final_model_candidates(
                        ocr_candidates,
                        detected_maker=detected_maker,
                        similar_results=similar_results
                    )

                    best_model = ""

                    if final_model_candidates:
                        best_model = final_model_candidates[0][0]

                    suggested_category = suggest_category(
                        maker=detected_maker,
                        memo="",
                        ocr_texts=all_texts,
                        image_types=[]
                    )

                    suggested_tags = suggest_tags(
                        maker=detected_maker,
                        category=suggested_category,
                        memo="",
                        ocr_texts=all_texts
                    )

                    st.session_state["easy_maker"] = detected_maker
                    st.session_state["easy_model_number"] = best_model
                    st.session_state["easy_category"] = suggested_category
                    st.session_state["easy_tags"] = suggested_tags
                    st.session_state["easy_ocr_texts"] = all_texts

                    st.rerun()

        if "easy_model_number" in st.session_state:
            st.subheader("AI推定結果")

            easy_maker = st.text_input(
                "メーカー",
                value=st.session_state.get("easy_maker", ""),
                key="easy_maker_input"
            )

            easy_model_number = st.text_input(
                "型番",
                value=st.session_state.get("easy_model_number", ""),
                key="easy_model_number_input"
            )

            easy_product_name = st.text_input(
                "商品名",
                value="未登録",
                key="easy_product_name_input"
            )

            easy_category_default = st.session_state.get("easy_category", "その他")

            if easy_category_default in categories[1:]:
                easy_category_index = categories[1:].index(easy_category_default)
            else:
                easy_category_index = 0

            easy_category = st.selectbox(
                "カテゴリ",
                categories[1:],
                index=easy_category_index,
                key="easy_category_input"
            )

            easy_tags = st.multiselect(
                "タグ",
                tag_options,
                default=st.session_state.get("easy_tags", []),
                key="easy_tags_input"
            )

            easy_memo = st.text_area(
                "メモ",
                value="",
                key="easy_memo_input"
            )

            if st.button("この内容で登録", key="easy_register_button"):
                if not easy_model_number:
                    st.warning("型番は入力してください。")
                elif is_duplicate_model(easy_model_number):
                    st.warning("この型番はすでに登録されています。")
                else:
                    image_path = save_uploaded_images(easy_image_list)

                    image_embedding = None

                    if image_path:
                        first_image_path = image_path.split(",")[0]
                        embedding = get_image_embedding(first_image_path)
                        image_embedding = embedding_to_blob(embedding)

                    product_id = add_product(
                        maker=easy_maker if easy_maker else "未登録",
                        product_name=easy_product_name if easy_product_name else "未登録",
                        model_number=easy_model_number,
                        category=easy_category,
                        image_path=image_path,
                        manual_url="",
                        install_url="",
                        official_url="",
                        memo=easy_memo,
                        tags=",".join(easy_tags),
                        image_embedding=image_embedding
                    )

                    if image_path:
                        for saved_path in image_path.split(","):
                            saved_path = saved_path.strip()

                            if saved_path:
                                add_product_image(
                                    product_id=product_id,
                                    image_path=saved_path,
                                    image_type="その他"
                                )

                    add_ai_feedback(
                        ocr_texts=st.session_state.get("easy_ocr_texts", []),
                        maker=easy_maker,
                        suggested_category=st.session_state.get("easy_category", ""),
                        final_category=easy_category,
                        suggested_tags=st.session_state.get("easy_tags", []),
                        final_tags=easy_tags
                    )

                    clear_keys = [
                        "easy_maker",
                        "easy_model_number",
                        "easy_category",
                        "easy_tags",
                        "easy_ocr_texts"
                    ]

                    for key in clear_keys:
                        if key in st.session_state:
                            del st.session_state[key]

                    st.success("AI簡単登録で登録しました。")
                    st.rerun()
                    
        with tab_detail:
            uploaded_images = st.file_uploader(
                "商品画像をアップロード（複数可）",
                type=["jpg", "jpeg", "png"],
                accept_multiple_files=True
            )

            if uploaded_images:
                os.makedirs("temp_images", exist_ok=True)

                first_uploaded_image = uploaded_images[0]

                temp_image_path = os.path.join(
                    "temp_images",
                    f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{first_uploaded_image.name}"
                )

                with open(temp_image_path, "wb") as f:
                    f.write(first_uploaded_image.getbuffer())

                st.subheader("アップロード画像一覧")

                image_type_inputs = {}

                for i, uploaded_image in enumerate(uploaded_images):
                    with st.container(border=True):
                        st.image(uploaded_image, width=220)

                        auto_key = f"auto_image_type_{i}_{uploaded_image.name}"

                        if auto_key not in st.session_state:
                            os.makedirs("temp_images", exist_ok=True)

                            temp_image_path_for_type = os.path.join(
                                "temp_images",
                                f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uploaded_image.name}"
                            )

                            with open(temp_image_path_for_type, "wb") as f:
                                f.write(uploaded_image.getbuffer())

                            texts_for_type = extract_text_from_image(temp_image_path_for_type)

                            st.session_state[auto_key] = suggest_image_type_from_texts(texts_for_type)

                        selected_auto_type = st.session_state.get(
                            auto_key,
                            "全体写真"
                        )

                        if selected_auto_type in image_type_options:
                            image_type_index = image_type_options.index(selected_auto_type)
                        else:
                            image_type_index = image_type_options.index("その他")

                        image_type = st.selectbox(
                            f"画像種類 {i + 1}",
                            image_type_options,
                            index=image_type_index,
                            key=f"register_image_type_{i}_{uploaded_image.name}"
                        )

                        image_type_inputs[i] = image_type

                if st.button("優先OCRで型番を読み取る"):
                    label_texts = []
                    other_texts = []
                    last_temp_image_path = ""

                    os.makedirs("temp_images", exist_ok=True)

                    for i, uploaded_image in enumerate(uploaded_images):
                        temp_image_path = os.path.join(
                            "temp_images",
                            f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uploaded_image.name}"
                        )

                        with open(temp_image_path, "wb") as f:
                            f.write(uploaded_image.getbuffer())

                        texts = extract_text_from_image(temp_image_path)

                        image_type = image_type_inputs.get(i, "その他")

                        if image_type == "型番ラベル":
                            label_texts.extend(texts)
                        else:
                            other_texts.extend(texts)

                        last_temp_image_path = temp_image_path

                    label_candidates = extract_model_candidates(label_texts)

                    if label_candidates:
                        all_texts = label_texts
                        ocr_candidates = label_candidates

                        st.success("型番ラベル画像から候補を検出しました。")

                    else:
                        all_texts = label_texts + other_texts

                        ocr_candidates = extract_model_candidates(all_texts)

                        st.warning("型番ラベル画像で見つからなかったため、全画像から検出しました。")

                    detected_maker = detect_maker_from_text(all_texts)

                    st.session_state["ocr_candidates"] = ocr_candidates
                    st.session_state["temp_image_path"] = last_temp_image_path
                    st.session_state["detected_maker"] = detected_maker
                    st.session_state["ocr_texts"] = all_texts

            if "ocr_candidates" in st.session_state:
                if st.session_state["ocr_candidates"]:
                    candidate_labels = [
                        f"{candidate}（スコア：{score}）"
                        for candidate, score in st.session_state["ocr_candidates"]
                    ]

                    selected_label = st.selectbox(
                        "型番候補を選択",
                        candidate_labels
                    )

                    selected_model = selected_label.split("（スコア：")[0]

                    st.session_state["ai_selected_model"] = selected_model

                    st.session_state["selected_model_number"] = selected_model

                    similar_results_for_model = []

                    if "temp_image_path" in st.session_state:
                        similar_results_for_model = search_similar_images_fast(
                            st.session_state["temp_image_path"],
                            top_k=5
                        )

                    final_model_candidates = decide_final_model_candidates(
                        st.session_state["ocr_candidates"],
                        detected_maker=st.session_state.get("detected_maker", ""),
                        similar_results=similar_results_for_model
                    )

                    if final_model_candidates:
                        best_model = final_model_candidates[0][0]
                        st.session_state["selected_model_number"] = best_model
                        st.info(f"型番確定AIの最有力候補：{best_model}")

                    if final_model_candidates:
                        st.subheader("型番確定AI候補")

                        for model, score in final_model_candidates:
                            st.write(f"**{model}**（確信スコア：{score:.1f}）")

                    similar_model_results = find_similar_model_numbers(
                        st.session_state["ocr_candidates"]
                    )

                    if similar_model_results:
                        st.subheader("既存DBの近い型番候補")

                        for result in similar_model_results:
                            st.write(
                                f"**OCR候補**：{result['ocr_candidate']} → "
                                f"**既存DB型番**：{result['db_model']} "
                                f"（類似度：{result['similarity']:.2f}）"
                            )

                    detected_maker = st.session_state.get("detected_maker", "")

                    st.subheader("OCR候補からGoogle検索")

                    for candidate, score in st.session_state["ocr_candidates"]:
                        if score < 90:
                            continue
                        col1, col2, col3 = st.columns(3)

                        with col1:
                            st.link_button(
                                f"{candidate} 施工説明書",
                                create_google_search_url(f"{candidate} 施工説明書")
                            )

                        with col2:
                            st.link_button(
                                f"{candidate} 取扱説明書",
                                create_google_search_url(f"{candidate} 取扱説明書")
                            )

                        with col3:
                            st.link_button(
                                f"{candidate} 商品ページ",
                                create_google_search_url(f"{candidate} 商品ページ")
                            )

            else:
                st.info("型番候補が見つかりませんでした。")

            if "ocr_texts" in st.session_state:
                with st.expander("OCRで読み取った文字を確認"):
                    st.write(st.session_state["ocr_texts"])

            if "temp_image_path" in st.session_state:
                processed_preview_path = st.session_state[
                "temp_image_path"
                ].replace(".", "_processed.")

                if os.path.exists(processed_preview_path):
                    with st.expander("OCR前処理後の画像"):
                        st.image(processed_preview_path, width=300)

            default_model_number = st.session_state.get(
                "ai_selected_model",
                st.session_state.get(
                    "selected_model_number",
                    ""
                )
            )

            default_maker = st.session_state.get("detected_maker", "")

            default_maker = st.session_state.get(
                "ai_detected_maker",
                ""
            )

            model_number = st.text_input(
                "型番",
                value=default_model_number
            )

            matched_product = None

            if model_number:
                matched_product = get_product_by_model_number(model_number)

            if matched_product is not None:
                st.info("既存DBから商品情報を見つけました。")

                if st.button("既存情報で補完する"):
                    st.session_state["auto_maker"] = matched_product["maker"]
                    st.session_state["auto_product_name"] = matched_product["product_name"]
                    st.session_state["auto_category"] = matched_product["category"]
                    st.rerun()

            maker = st.text_input(
                "メーカー名 例：TOTO、LIXIL、Panasonic",
                value=st.session_state.get("auto_maker", "")
            )

            existing_candidates = []

            uploaded_image_path_for_check = st.session_state.get("temp_image_path", "")

            if model_number:
                existing_candidates = find_existing_product_candidates(
                    model_number=model_number,
                    maker=maker,
                    uploaded_image_path=uploaded_image_path_for_check
                )

            if existing_candidates:
                st.subheader("既存商品候補")
                st.warning("同じ商品がすでに登録されている可能性があります。")

                for idx, item in enumerate(existing_candidates):
                    row = item["row"]
                    score = item["score"]

                    with st.container(border=True):
                        col_img, col_info = st.columns([1, 2])

                        with col_img:
                            show_first_product_image(
                                row["id"],
                                row["image_path"],
                                width=180
                            )

                        with col_info:
                            st.write(f"**候補スコア**：{score:.1f}")
                            st.write(f"**メーカー**：{row['maker']}")
                            st.write(f"**商品名**：{row['product_name']}")
                            st.write(f"**型番**：{row['model_number']}")
                            st.write(f"**カテゴリ**：{row['category']}")
                            st.write(f"**メモ**：{row['memo']}")

                            if st.button(
                                "この既存商品を編集する",
                                key=f"edit_existing_candidate_{row['id']}_{idx}"
                            ):
                                st.session_state["edit_product_id"] = row["id"]
                                st.success("商品編集メニューを開いてください。")

                            if st.button(
                                "この商品に画像を追加する",
                                key=f"add_image_to_existing_{row['id']}_{idx}"
                            ):
                                if uploaded_images:
                                    added_count = add_uploaded_images_to_product(
                                        product_id=row["id"],
                                        uploaded_images=uploaded_images,
                                        image_type="その他"
                                    )

                                    build_faiss_index.clear()

                                    st.success(f"{added_count}枚の画像を既存商品に追加しました。")
                                    st.rerun()
                                else:
                                    st.warning("追加する画像がありません。")

            suggested_product_name = suggest_product_name_from_model(
                maker=maker,
                model_number=model_number
            )

            product_name = st.text_input(
                "商品名",
                value=st.session_state.get("auto_product_name", suggested_product_name)
            )

            ocr_texts = st.session_state.get("ocr_texts", [])

            image_types = list(image_type_inputs.values()) if "image_type_inputs" in locals() else []

            suggested_category = suggest_category(
                maker=maker,
                memo="",
                ocr_texts=ocr_texts,
                image_types=image_types
            )

            st.info(f"AIカテゴリ候補：{suggested_category}")

            auto_category = st.session_state.get(
                "auto_category",
                suggested_category
            )

            if auto_category in categories[1:]:
                category_index = categories[1:].index(auto_category)
            else:
                category_index = 0

            category = st.selectbox(
                "カテゴリ",
                categories[1:],
                index=category_index
            )

            manual_url = st.text_input("取扱説明書URL")
            install_url = st.text_input("施工説明書URL")
            official_url = st.text_input("公式ページURL")

            memo = st.text_area("現場メモ・注意点")

            ocr_texts = st.session_state.get("ocr_texts", [])

            suggested_tags = suggest_tags(
                maker=maker,
                category=category,
                memo=memo,
                ocr_texts=ocr_texts
            )

            if suggested_tags:
                st.info(f"AIタグ候補：{', '.join(suggested_tags)}")

            selected_tags = st.multiselect(
                "タグを選択",
                tag_options,
                default=suggested_tags
            )

            tags = ",".join(selected_tags)

            if st.button("登録する"):
                if model_number:
                    if is_duplicate_model(model_number):
                        st.warning("この型番はすでに登録されています。")
                        st.stop()

                    image_path = save_uploaded_images(uploaded_images)

                    image_embedding = None

                    image_path = save_uploaded_images(uploaded_images)

                    image_embedding = None

                    if image_path:
                        first_image_path = image_path.split(",")[0]
                        embedding = get_image_embedding(first_image_path)
                        image_embedding = embedding_to_blob(embedding)

                    product_id = add_product(
                        maker=maker if maker else "未登録",
                        product_name=product_name if product_name else "未登録",
                        model_number=model_number,
                        category=category,
                        image_path=image_path,
                        manual_url=manual_url,
                        install_url=install_url,
                        official_url=official_url,
                        memo=memo,
                        tags=tags,
                        image_embedding=image_embedding
                    )

                    ocr_texts = st.session_state.get("ocr_texts", [])

                    add_ai_feedback(
                        ocr_texts=ocr_texts,
                        maker=maker,
                        suggested_category=suggested_category,
                        final_category=category,
                        suggested_tags=suggested_tags,
                        final_tags=selected_tags
                    )

                    if image_path:
                        saved_paths = image_path.split(",")

                        for i, saved_path in enumerate(saved_paths):
                            saved_path = saved_path.strip()

                            if saved_path:
                                image_type = image_type_inputs.get(i, "その他")

                                add_product_image(
                                    product_id=product_id,
                                    image_path=saved_path,
                                    image_type=image_type
                                )

                    if image_path:
                        for saved_path in image_path.split(","):
                            add_product_image(
                                product_id=product_id,
                                image_path=saved_path.strip(),
                                image_type="その他"
                            )

                    clear_keys = [
                        "ocr_candidates",
                        "temp_image_path",
                        "detected_maker",
                        "ocr_texts",
                        "ai_selected_model",
                        "selected_model_number",
                        "auto_maker",
                        "auto_product_name",
                        "auto_category",
                        "ai_detected_maker"
                    ]

                    for key in clear_keys:
                        if key in st.session_state:
                            del st.session_state[key]

                    st.success("登録しました。")
                    st.rerun()
                else:
                    st.warning("型番は入力してください。")

elif menu == "登録一覧":
    st.header("登録済み商品一覧")

    sort_option = st.selectbox(
        "並び替え",
        [
            "登録順",
            "メーカー順",
            "商品名順",
            "型番順"
        ]
    )

    sort_map = {
        "登録順": "created_at",
        "メーカー順": "maker",
        "商品名順": "product_name",
        "型番順": "model_number"
    }

    df = get_all_products(
        sort_by=sort_map[sort_option]
    )

    if df.empty:
        st.info("まだ登録がありません。")
    else:
        for _, row in df.iterrows():
            with st.expander(f"{row['maker']} / {row['product_name']} / {row['model_number']}"):
                col_img, col_info = st.columns([1, 2])

                with col_img:
                    if row["image_path"]:
                        show_product_images(row["image_path"], width=220)
                    else:
                        st.write("画像なし")
                with col_info:
                    st.write(f"**メーカー**：{row['maker']}")
                    st.write(f"**商品名**：{row['product_name']}")
                    st.write(f"**型番**：{row['model_number']}")
                    st.write(f"**カテゴリ**：{row['category']}")
                    st.write(f"**登録日**：{row['created_at']}")
                    st.write(f"**メモ**：{row['memo']}")

                    if row["manual_url"]:
                        st.link_button("取扱説明書", row["manual_url"])

                    if row["install_url"]:
                        st.link_button("施工説明書", row["install_url"])

                    if row["official_url"]:
                        st.link_button("公式ページ", row["official_url"])

elif menu == "商品編集":
    st.header("商品情報を編集する")

    df = get_all_products()

    if df.empty:
        st.info("まだ登録がありません。")
    else:
        product_options = {
            f"{row['id']}：{row['maker']} / {row['product_name']} / {row['model_number']}": row["id"]
            for _, row in df.iterrows()
        }

        default_index = 0

        if "edit_product_id" in st.session_state:
            ids = list(product_options.values())

            if st.session_state["edit_product_id"] in ids:
                default_index = ids.index(st.session_state["edit_product_id"])

        selected_label = st.selectbox(
            "編集する商品を選んでください",
            list(product_options.keys()),
            index=default_index
        )

        selected_id = product_options[selected_label]
        selected_product = df[df["id"] == selected_id].iloc[0]

        tab_basic, tab_images, tab_delete = st.tabs([
            "基本情報",
            "画像管理",
            "削除"
        ])

        with tab_images:

            st.subheader("画像管理")

            image_df = get_product_images(selected_id)

            if image_df.empty:
                current_image_path = selected_product["image_path"]

                if current_image_path:
                    show_product_images(current_image_path, width=220)
                else:
                    st.write("画像なし")
            else:
                for _, image_row in image_df.iterrows():
                    image_id = image_row["id"]
                    image_path = image_row["image_path"]
                    current_type = image_row["image_type"]

                    with st.container(border=True):
                        col_img, col_control = st.columns([1, 2])

                        with col_img:
                            show_image_safely(image_path, width=220)

                        with col_control:
                            st.write(f"**画像ID**：{image_id}")

                            if current_type in image_type_options:
                                type_index = image_type_options.index(current_type)
                            else:
                                type_index = image_type_options.index("その他")

                            new_image_type = st.selectbox(
                                "画像種類",
                                image_type_options,
                                index=type_index,
                                key=f"image_type_{image_id}"
                            )

                            if st.button(
                                "画像種類を更新",
                                key=f"update_image_type_{image_id}"
                            ):
                                update_product_image_type(image_id, new_image_type)
                                st.success("画像種類を更新しました。")
                                st.rerun()

                            confirm_image_delete = st.checkbox(
                                "この画像を削除する",
                                key=f"confirm_delete_image_{image_id}"
                            )

                            if st.button(
                                "画像を削除",
                                key=f"delete_image_{image_id}"
                            ):
                                if confirm_image_delete:
                                    delete_product_image(image_id)

                                    build_faiss_index.clear()

                                    st.success("画像を削除しました。")
                                    st.rerun()
                                else:
                                    st.warning("削除するにはチェックを入れてください。")

            st.subheader("画像を追加")

            additional_images = st.file_uploader(
                "追加する画像をアップロード（複数可）",
                type=["jpg", "jpeg", "png"],
                accept_multiple_files=True,
                key=f"additional_images_{selected_id}"
            )

            additional_image_type = st.selectbox(
                "追加画像の種類",
                image_type_options,
                key=f"additional_image_type_{selected_id}"
            )

            if st.button(
                "画像を追加する",
                key=f"add_images_{selected_id}"
            ):
                added_count = add_uploaded_images_to_product(
                    selected_id,
                    additional_images,
                    additional_image_type
                )

                build_faiss_index.clear()

                st.success(f"{added_count}枚の画像を追加しました。")
                st.rerun()

        with tab_basic:

            st.subheader("商品情報を編集")

            maker = st.text_input(
                "メーカー名",
                value=selected_product["maker"]
            )

            product_name = st.text_input(
                "商品名",
                value=selected_product["product_name"]
            )

            model_number = st.text_input(
                "型番",
                value=selected_product["model_number"]
            )

            current_category = selected_product["category"]

            if current_category in categories:
                category_index = categories.index(current_category)
            else:
                category_index = 0

            category = st.selectbox(
                "カテゴリ",
                categories[1:],
                index=max(category_index - 1, 0)
            )

            uploaded_image = st.file_uploader(
                "画像を差し替える場合だけアップロード",
                type=["jpg", "jpeg", "png"]
            )

            manual_url = st.text_input(
                "取扱説明書URL",
                value=selected_product["manual_url"]
            )

            install_url = st.text_input(
                "施工説明書URL",
                value=selected_product["install_url"]
            )

            official_url = st.text_input(
                "公式ページURL",
                value=selected_product["official_url"]
            )

            memo = st.text_area(
                "現場メモ・注意点",
                value=selected_product["memo"]
            )

            current_tags = []

            if selected_product["tags"]:
                current_tags = (
                    selected_product["tags"].split(",")
                    if pd.notna(selected_product["tags"])
                    else []
                )

            selected_tags = st.multiselect(
                "タグを選択",
                tag_options,
                default=current_tags
            )

            tags = ",".join(selected_tags)

            if st.button("更新する"):
                new_image_path = current_image_path

                if uploaded_image is not None:
                    new_image_path = save_uploaded_image(uploaded_image)

                update_product(
                    product_id=selected_id,
                    maker=maker,
                    product_name=product_name,
                    model_number=model_number,
                    category=category,
                    image_path=new_image_path,
                    manual_url=manual_url,
                    install_url=install_url,
                    official_url=official_url,
                    memo=memo,
                    tags=tags
                )

                st.success("商品情報を更新しました。")
                st.rerun()

        with tab_delete:

            st.divider()

            st.subheader("この商品を削除")

            confirm_delete = st.checkbox(
                "本当にこの商品を削除する",
                key=f"edit_delete_confirm_{selected_id}"
            )

            if st.button(
                "この商品を削除する",
                key=f"edit_delete_button_{selected_id}"
            ):
                if confirm_delete:
                    delete_product(selected_id)
                    st.success("商品を削除しました。")
                    st.rerun()
                else:
                    st.warning("削除するにはチェックを入れてください。")


elif menu == "施工説明書URL登録":
    st.header("施工説明書URLを登録する")

    df = get_all_products()

    if df.empty:
        st.info("まだ登録がありません。")
    else:
        product_options = {
            f"{row['id']}：{row['maker']} / {row['product_name']} / {row['model_number']}": row["id"]
            for _, row in df.iterrows()
        }

        selected_label = st.selectbox(
            "商品を選んでください",
            list(product_options.keys())
        )

        selected_id = product_options[selected_label]
        selected_product = df[df["id"] == selected_id].iloc[0]

        st.subheader("商品情報")
        st.write(f"**メーカー**：{selected_product['maker']}")
        st.write(f"**商品名**：{selected_product['product_name']}")
        st.write(f"**型番**：{selected_product['model_number']}")
        st.write(f"**現在の施工説明書URL**：{selected_product['install_url']}")

        maker = selected_product["maker"]
        model_number = selected_product["model_number"]

        if maker and maker != "未登録":
            query = f"{maker} {model_number} 施工説明書"
        else:
            query = f"{model_number} 施工説明書"

        google_url = create_google_search_url(query)

        st.link_button(
            "Googleで施工説明書を探す",
            google_url
        )

        st.subheader("AI施工説明書候補")

        if st.button("AIで施工説明書候補を探す"):
            pdf_candidates = find_pdf_candidates(
                maker=maker,
                model_number=model_number,
                document_type="施工説明書"
            )

            st.session_state["install_pdf_candidates"] = pdf_candidates

        if "install_pdf_candidates" in st.session_state:
            pdf_candidates = st.session_state["install_pdf_candidates"]

            if not pdf_candidates:
                st.info("施工説明書候補は見つかりませんでした。")
            else:
                for idx, candidate in enumerate(pdf_candidates):
                    with st.container(border=True):
                        st.write(f"**候補{idx + 1}**")
                        st.write(candidate["title"])
                        st.write(f"スコア：{candidate['score']}")

                        st.link_button(
                            "候補を開く",
                            candidate["url"],
                            key=f"open_install_candidate_{idx}"
                        )

                        if st.button(
                            "このURLを施工説明書として保存",
                            key=f"save_install_candidate_{idx}"
                        ):
                            update_install_url(
                                selected_id,
                                candidate["url"]
                            )

                            st.success("施工説明書URLを保存しました。")
                            st.rerun()

        new_install_url = st.text_input(
            "見つけた施工説明書URLを貼り付け",
            value=selected_product["install_url"] if selected_product["install_url"] else ""
        )

        if st.button("施工説明書URLを保存"):
            if new_install_url:
                update_install_url(selected_id, new_install_url)
                st.success("施工説明書URLを保存しました。")
                st.rerun()
            else:
                st.warning("URLを入力してください。")

elif menu == "OCR履歴":
    st.header("OCR履歴")

    df = get_ocr_history()

    if df.empty:
        st.info("OCR履歴はまだありません。")
    else:
        for _, row in df.iterrows():
            with st.expander(f"{row['created_at']} / {row['detected_maker']}"):
                if row["image_path"] and os.path.exists(row["image_path"]):
                    st.image(row["image_path"], width=250)

                if st.button(
                    "この履歴で再検索",
                    key=f"rerun_ocr_history_{row['id']}"
                ):
                    texts, ocr_candidates, detected_maker, similar_results, combined_results = run_ai_search_from_image(
                        row["image_path"]
                    )

                    st.session_state["ai_texts"] = texts
                    st.session_state["ai_ocr_candidates"] = ocr_candidates
                    st.session_state["ai_detected_maker"] = detected_maker
                    st.session_state["ai_similar_results"] = similar_results
                    st.session_state["ai_combined_results"] = combined_results

                    st.success("この履歴で再検索しました。通常検索メニューで結果を確認できます。")

                st.write(f"**検出メーカー**：{row['detected_maker']}")
                st.write(f"**型番候補**：{row['candidates']}")

                candidates = row["candidates"].split(",")

                for candidate_text in candidates:
                    if ":" in candidate_text:
                        candidate, score = candidate_text.split(":")

                        if int(float(score)) >= 90:
                            base_query = candidate

                            if row["detected_maker"]:
                                base_query = f"{row['detected_maker']} {candidate}"

                            st.link_button(
                                f"{base_query} 施工説明書を検索",
                                create_google_search_url(f"{base_query} 施工説明書")
                            )