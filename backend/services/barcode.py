"""バーコード・QR コードの読み取り結果の解釈と、商品の検索。"""

import json
import re
from difflib import SequenceMatcher
from urllib.parse import parse_qs, unquote, urlparse

from services.matching import fetch_all_products, product_row_to_result


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
