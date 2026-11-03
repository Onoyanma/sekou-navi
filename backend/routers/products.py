"""商品の登録・取得・更新・削除と、商品画像の管理。"""

import os
import sqlite3

from fastapi import APIRouter, File, HTTPException, UploadFile

import ai as product_ai
from database import DB_PATH as DB_NAME, IMAGE_DIR, unique_filename
from schemas import ProductCreate, ProductUpdate
from services.embeddings import (
    build_embedding_blob,
    resolve_image_file_path,
    save_product_text_embedding,
)
from services.matching import fetch_all_products

router = APIRouter()


@router.get("/products")
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


@router.get("/products/summary")
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


@router.get("/products/{product_id}")
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


@router.post("/products")
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


@router.post("/products/{product_id}/images")
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


@router.put("/products/{product_id}")
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


@router.post("/products/auto-tags/rebuild")
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


@router.post("/products/{product_id}/auto-tags")
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


@router.delete("/products/{product_id}")
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


@router.get("/products/{product_id}/images")
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


@router.delete("/products/{product_id}/images/{image_id}")
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
