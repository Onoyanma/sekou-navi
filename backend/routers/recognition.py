"""写真から商品を見分ける（OCR・画像の類似検索・型番の照合）。"""

import os
import shutil
import sqlite3
import traceback
from difflib import SequenceMatcher
from typing import List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile

from database import DB_PATH as DB_NAME, TEMP_DIR, unique_filename
from services.embeddings import get_image_embedding, normalize_embedding_vector
from services.files import remove_temp_files
from services.matching import (
    MIN_SIMILARITY,
    compute_similar_results,
    fetch_all_products,
    find_similar_model_numbers,
    merge_similar_search_results,
)
from services.model_numbers import (
    detect_maker_from_text,
    extract_model_candidates,
    extract_product_name_hints,
)
from services.ocr import extract_text_from_image

router = APIRouter()


@router.post("/ocr")
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


@router.post("/similar-search")
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
            # 1 位の確度。結果が無ければ none（画面で「自信がない」ときの見せ方を変えるために使う）
            "top_confidence": results[0]["confidence"] if results else "none",
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


@router.post("/match-products")
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
