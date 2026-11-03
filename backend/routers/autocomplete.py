"""型番・URL からの登録フォームの自動補完。"""

import sqlite3
import traceback
from difflib import SequenceMatcher

from fastapi import APIRouter, Body, HTTPException

import ai as product_ai
from database import DB_PATH as DB_NAME
from schemas import ProductAutocompleteRequest
from services.matching import fetch_all_products

router = APIRouter()


@router.post("/autocomplete-product")
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


@router.post("/suggest-product-name")
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
