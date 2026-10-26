"""
型番・商品ページURLから商品登録フォームを自動補完するロジック。
外部LLM APIは使わず、Webページ取得・構造化データ・DB類似・ルール推論で構成。
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup

REQUEST_TIMEOUT = 12
USER_AGENT = (
    "Mozilla/5.0 (compatible; SekouNaviBot/1.0; +https://localhost/product-autocomplete)"
)

MAKER_ALIASES: dict[str, list[str]] = {
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

DOMAIN_MAKERS: dict[str, str] = {
    "toto.co.jp": "TOTO",
    "jp.toto.com": "TOTO",
    "lixil.co.jp": "LIXIL",
    "inax.co.jp": "LIXIL",
    "panasonic.com": "Panasonic",
    "daiken.jp": "DAIKEN",
    "ykkap.co.jp": "YKK AP",
    "cleanup.jp": "クリナップ",
    "takara-standard.co.jp": "タカラスタンダード",
    "mitsubishielectric.co.jp": "三菱電機",
    "hitachi.co.jp": "日立",
    "rinnai.co.jp": "リンナイ",
    "noritz.co.jp": "ノーリツ",
}

MODEL_PREFIX_RULES: list[tuple[str, str, str, str]] = [
    # prefix, category, product_name, tags
    ("TCF", "トイレ", "トイレ関連部材", "水回り,トイレ"),
    ("CS", "トイレ", "トイレ関連部材", "水回り,トイレ"),
    ("TKS", "キッチン", "水栓", "水回り,キッチン"),
    ("SF", "キッチン", "水栓", "水回り,キッチン"),
    ("FY", "換気扇", "換気扇", "換気"),
    ("VD", "換気扇", "換気扇", "換気"),
    ("LH", "洗面台", "洗面", "水回り,洗面"),
    ("AW", "浴室", "浴室部材", "水回り,浴室"),
]

CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("トイレ", ["トイレ", "便器", "便座", "ウォシュレット", "タンク", "toilet"]),
    ("キッチン", ["キッチン", "水栓", "シンク", "混合栓", "kitchen", "faucet"]),
    ("洗面台", ["洗面", "洗面台", "lavatory", "vanity"]),
    ("浴室", ["浴室", "バス", "浴槽", "シャワー", "bath"]),
    ("換気扇", ["換気", "換気扇", "ファン", "ventilation"]),
    ("給排水部材", ["給排水", "配管", "止水", "バルブ", "継手"]),
    ("電気設備", ["電気", "スイッチ", "コンセント", "照明", "led"]),
    ("建具", ["建具", "ドア", "扉", "引き戸"]),
    ("サッシ", ["サッシ", "窓", "シャッター"]),
    ("床材", ["床材", "フロoring", "フロア", "床"]),
    ("壁材", ["壁材", "クロス", "パネル", "壁"]),
]

MODEL_IGNORE = {
    "TOTO", "LIXIL", "PANASONIC", "YKK", "DAIKEN", "INAX",
    "MADE", "JAPAN", "MODEL", "TYPE", "HTML", "HTTP", "HTTPS",
    "WWW", "CO", "JP", "COM",
}

CATEGORY_TAGS: dict[str, list[str]] = {
    "キッチン": ["キッチン", "水回り"],
    "トイレ": ["トイレ", "水回り"],
    "洗面台": ["洗面", "水回り"],
    "浴室": ["浴室", "水回り"],
    "建具": ["建具"],
    "床材": ["床材"],
    "壁材": ["壁材"],
    "サッシ": ["サッシ", "窓"],
    "電気設備": ["電気"],
    "換気扇": ["換気扇", "換気"],
    "給排水部材": ["給排水", "水回り"],
    "工具": ["工具"],
    "その他": [],
}

MAKER_TAGS: dict[str, list[str]] = {
    "TOTO": ["TOTO"],
    "LIXIL": ["LIXIL", "INAX"],
    "Panasonic": ["Panasonic"],
    "YKK AP": ["YKK"],
    "DAIKEN": ["DAIKEN"],
    "クリナップ": ["クリナップ"],
    "タカラスタンダード": ["タカラ"],
    "三菱電機": ["三菱"],
    "日立": ["日立"],
    "リンナイ": ["リンナイ"],
    "ノーリツ": ["ノーリツ"],
}

PRODUCT_NAME_TAG_KEYWORDS: list[tuple[str, str]] = [
    ("ウォシュレット", "便座"),
    ("便座", "便座"),
    ("便器", "トイレ"),
    ("水栓", "水栓"),
    ("混合栓", "水栓"),
    ("止水", "止水栓"),
    ("シャワー", "シャワー"),
    ("換気扇", "換気扇"),
    ("レンジフード", "換気扇"),
    ("洗面", "洗面"),
    ("浴槽", "浴室"),
    ("ドア", "建具"),
    ("引き戸", "建具"),
    ("サッシ", "サッシ"),
    ("照明", "照明"),
    ("スイッチ", "電気"),
    ("部品", "部品"),
    ("パッキン", "部品"),
    ("フィルター", "部品"),
]

SKIP_TAGS = {
    "未登録",
    "",
    "その他",
    "商品",
    "部材",
}

MAX_AUTO_TAGS = 10


def parse_tags(tags_value: str) -> list[str]:
    if not tags_value:
        return []

    parts = re.split(r"[,、/／\s]+", str(tags_value).strip())
    seen: set[str] = set()
    result: list[str] = []

    for part in parts:
        tag = part.strip()
        if not tag or tag in SKIP_TAGS:
            continue
        key = tag.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(tag)

    return result


def format_tags(tags: list[str]) -> str:
    return ",".join(tags[:MAX_AUTO_TAGS])


def merge_tag_lists(*tag_lists: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()

    for tag_list in tag_lists:
        for tag in tag_list:
            normalized = tag.strip()
            if not normalized or normalized in SKIP_TAGS:
                continue
            key = normalized.casefold()
            if key in seen:
                continue
            seen.add(key)
            merged.append(normalized)

    return merged[:MAX_AUTO_TAGS]


def generate_tags_for_product(product: dict[str, Any]) -> list[str]:
    """商品情報からAIタグ候補を生成する（外部LLM不使用）。"""
    maker = str(product.get("maker") or "").strip()
    product_name = str(product.get("product_name") or "").strip()
    model_number = str(product.get("model_number") or "").strip().upper()
    category = str(product.get("category") or "").strip()
    memo = str(product.get("memo") or "").strip()
    official_url = str(product.get("official_url") or "").strip()

    tag_lists: list[list[str]] = []

    if category and category in CATEGORY_TAGS:
        tag_lists.append(CATEGORY_TAGS[category])
    elif category and category not in SKIP_TAGS:
        tag_lists.append([category])

    if maker:
        if maker in MAKER_TAGS:
            tag_lists.append(MAKER_TAGS[maker])
        elif maker not in SKIP_TAGS:
            tag_lists.append([maker])

    prefix_info = infer_from_model_prefix(model_number)
    if prefix_info.get("tags"):
        tag_lists.append(parse_tags(prefix_info["tags"]))

    combined_text = " ".join(
        filter(None, [product_name, model_number, memo, official_url])
    ).upper()

    for keyword, tag in PRODUCT_NAME_TAG_KEYWORDS:
        if keyword.upper() in combined_text or keyword in product_name:
            tag_lists.append([tag])

    if official_url:
        tag_lists.append(["公式情報"])
        url_maker = detect_maker_from_url(official_url)
        if url_maker and url_maker in MAKER_TAGS:
            tag_lists.append(MAKER_TAGS[url_maker])

    if model_number and len(model_number) >= 4:
        tag_lists.append(["型番登録"])

    if memo and ("QR" in memo.upper() or "バーコード" in memo):
        tag_lists.append(["コード読取"])

    if product_name and product_name not in SKIP_TAGS and product_name != model_number:
        short_name = product_name
        if len(short_name) <= 12 and not re.fullmatch(
            r"[A-Z0-9\-]+", short_name.upper()
        ):
            tag_lists.append([short_name])

    inferred_category = infer_category_from_text(combined_text)
    if inferred_category and inferred_category != category:
        tag_lists.append(CATEGORY_TAGS.get(inferred_category, [inferred_category]))

    return merge_tag_lists(*tag_lists)


def apply_auto_tags(
    product: dict[str, Any],
    existing_tags: str = "",
) -> tuple[str, list[str]]:
    """
    既存タグとAI生成タグをマージする。
    戻り値: (保存用タグ文字列, AIが新たに追加したタグ一覧)
    """
    user_tags = parse_tags(existing_tags)
    generated = generate_tags_for_product(product)
    merged = merge_tag_lists(user_tags, generated)
    added = [tag for tag in generated if tag not in user_tags]
    return format_tags(merged), added


def detect_maker_from_text(text: str) -> str:
    upper = text.upper()
    for maker, aliases in MAKER_ALIASES.items():
        for alias in aliases:
            if alias.upper() in upper:
                return maker
    return ""


def detect_maker_from_url(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""

    for domain, maker in DOMAIN_MAKERS.items():
        if domain in host:
            return maker
    return ""


def infer_category_from_text(text: str) -> str:
    lower = text.lower()
    for category, keywords in CATEGORY_KEYWORDS:
        for keyword in keywords:
            if keyword.lower() in lower:
                return category
    return ""


def infer_from_model_prefix(model_number: str) -> dict[str, str]:
    upper = model_number.upper().strip()
    for prefix, category, product_name, tags in MODEL_PREFIX_RULES:
        if upper.startswith(prefix):
            return {
                "category": category,
                "product_name": product_name,
                "tags": tags,
            }
    return {}


def extract_model_candidates(text: str, limit: int = 8) -> list[dict[str, Any]]:
    cleaned = text.replace("　", " ").replace("ー", "-").replace("－", "-")
    matches = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-_/.]{3,}", cleaned)
    scored: dict[str, int] = {}

    for match in matches:
        token = match.strip(".,:;()[]{}<>").upper()
        if token in MODEL_IGNORE or len(token) < 4 or len(token) > 24:
            continue
        if token.isdigit() or token.isalpha():
            continue

        score = 0
        if any(c.isalpha() for c in token) and any(c.isdigit() for c in token):
            score += 50
        if "-" in token:
            score += 15
        if 5 <= len(token) <= 15:
            score += 15

        scored[token] = max(scored.get(token, 0), score)

    ranked = sorted(scored.items(), key=lambda item: item[1], reverse=True)
    return [
        {"model_number": model, "score": score}
        for model, score in ranked[:limit]
    ]


def clean_product_title(title: str) -> str:
    if not title:
        return ""

    cleaned = re.sub(r"\s+", " ", title).strip()
    cleaned = re.split(r"[|｜/／]", cleaned)[0].strip()
    cleaned = re.sub(
        r"\s*[-–—]\s*(TOTO|LIXIL|INAX|Panasonic|YKK|DAIKEN).*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s*[\|｜].*$", "", cleaned)
    cleaned = re.sub(r"^(TOTO|LIXIL|INAX)\s+", "", cleaned, flags=re.IGNORECASE)

    if len(cleaned) > 80:
        cleaned = cleaned[:80].rstrip()

    return cleaned


def parse_json_ld_products(soup: BeautifulSoup) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []

    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text()
        if not raw:
            continue

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue

        nodes = payload if isinstance(payload, list) else [payload]
        for node in nodes:
            if not isinstance(node, dict):
                continue

            graph = node.get("@graph")
            if isinstance(graph, list):
                nodes.extend(graph)
                continue

            node_type = node.get("@type", "")
            types = node_type if isinstance(node_type, list) else [node_type]
            if not any(
                t in ("Product", "IndividualProduct") for t in types if t
            ):
                continue

            brand = node.get("brand")
            maker = ""
            if isinstance(brand, dict):
                maker = str(brand.get("name") or "")
            elif isinstance(brand, str):
                maker = brand

            products.append({
                "product_name": str(node.get("name") or ""),
                "model_number": str(
                    node.get("sku")
                    or node.get("mpn")
                    or node.get("model")
                    or ""
                ),
                "maker": maker,
                "description": str(node.get("description") or ""),
                "category": str(node.get("category") or ""),
            })

    return products


def fetch_page_context(url: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "url": url,
        "title": "",
        "description": "",
        "text": "",
        "error": "",
        "json_ld_products": [],
    }

    try:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        response.raise_for_status()
        if "text/html" not in response.headers.get("Content-Type", "text/html"):
            result["error"] = "HTMLページではありません"
            return result

        html = response.text
    except Exception as exc:
        result["error"] = str(exc)
        return result

    soup = BeautifulSoup(html, "html.parser")

    title = ""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    elif soup.title and soup.title.string:
        title = soup.title.string.strip()

    description = ""
    og_desc = soup.find("meta", property="og:description")
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if og_desc and og_desc.get("content"):
        description = og_desc["content"].strip()
    elif meta_desc and meta_desc.get("content"):
        description = meta_desc["content"].strip()

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text)

    result.update({
        "ok": True,
        "title": title,
        "description": description,
        "text": text[:12000],
        "json_ld_products": parse_json_ld_products(soup),
    })
    return result


def extract_model_from_url(url: str) -> str:
    parsed = urlparse(url)
    parts = [parsed.path, parsed.query, unquote(parsed.fragment or "")]
    joined = " ".join(parts)
    candidates = extract_model_candidates(joined, limit=3)
    if candidates:
        return candidates[0]["model_number"]

    query = parse_qs(parsed.query)
    for key in ("model", "model_number", "sku", "品番", "型番", "code"):
        values = query.get(key) or query.get(key.upper())
        if values and values[0].strip():
            return values[0].strip().upper()

    return ""


def find_similar_product(model_number: str, products: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not model_number:
        return None

    target = model_number.upper()
    best_match = None
    best_score = 0.0

    for row in products:
        db_model = str(row.get("model_number") or "").upper()
        if not db_model:
            continue

        if target == db_model:
            score = 100.0
        else:
            similarity = SequenceMatcher(None, target, db_model).ratio()
            if similarity < 0.82:
                continue
            score = similarity * 100
            if target[:3] == db_model[:3]:
                score += 10

        if score > best_score:
            best_score = score
            best_match = {**row, "_match_score": score}

    return best_match


def merge_suggestion(
    base: dict[str, Any],
    patch: dict[str, Any],
    source: str,
    confidence: float,
) -> None:
    for key, value in patch.items():
        if value in (None, ""):
            continue
        if not base.get(key):
            base[key] = value
            base.setdefault("_field_sources", {})[key] = source
            base.setdefault("_field_confidence", {})[key] = confidence


def build_product_autocomplete(
    *,
    model_number: str = "",
    url: str = "",
    products: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    products = products or []
    model_number = (model_number or "").strip().upper()
    url = (url or "").strip()

    suggestion: dict[str, Any] = {
        "maker": "",
        "product_name": "",
        "model_number": model_number,
        "category": "",
        "tags": "",
        "memo": "",
        "official_url": url if url else "",
        "manual_url": "",
        "install_url": "",
        "confidence": 0.0,
        "sources": [],
        "model_candidates": [],
        "page_title": "",
        "matched_product": None,
        "notes": [],
    }

    texts: list[str] = []
    if model_number:
        texts.append(model_number)

    # --- URL解析 ---
    if url:
        suggestion["sources"].append("url")
        page = fetch_page_context(url)

        if page.get("ok"):
            page_text = " ".join(
                filter(
                    None,
                    [page.get("title"), page.get("description"), page.get("text")],
                )
            )
            texts.append(page_text)
            suggestion["page_title"] = page.get("title") or ""

            maker = detect_maker_from_url(url) or detect_maker_from_text(page_text)
            product_name = clean_product_title(page.get("title") or "")
            category = infer_category_from_text(page_text)

            merge_suggestion(
                suggestion,
                {
                    "maker": maker,
                    "product_name": product_name,
                    "category": category,
                    "official_url": url,
                },
                "url",
                0.75,
            )

            for item in page.get("json_ld_products") or []:
                merge_suggestion(
                    suggestion,
                    {
                        "maker": item.get("maker") or detect_maker_from_text(
                            item.get("product_name", "")
                        ),
                        "product_name": clean_product_title(
                            item.get("product_name") or ""
                        ),
                        "model_number": str(item.get("model_number") or "").upper(),
                        "category": infer_category_from_text(
                            " ".join(
                                [
                                    item.get("product_name") or "",
                                    item.get("description") or "",
                                    item.get("category") or "",
                                ]
                            )
                        ),
                    },
                    "json_ld",
                    0.9,
                )

            url_model = extract_model_from_url(url)
            if url_model and not suggestion.get("model_number"):
                suggestion["model_number"] = url_model

            candidates = extract_model_candidates(page_text, limit=6)
            suggestion["model_candidates"] = candidates
            if candidates and not suggestion.get("model_number"):
                suggestion["model_number"] = candidates[0]["model_number"]
        else:
            suggestion["notes"].append(
                f"URLの取得に失敗しました: {page.get('error') or '不明なエラー'}"
            )
            url_model = extract_model_from_url(url)
            if url_model:
                suggestion["model_number"] = url_model
                merge_suggestion(
                    suggestion,
                    {"maker": detect_maker_from_url(url)},
                    "url_path",
                    0.5,
                )

    resolved_model = (suggestion.get("model_number") or model_number).upper()
    if resolved_model:
        suggestion["model_number"] = resolved_model
        texts.append(resolved_model)

    # --- 型番プレフィックスルール ---
    prefix_info = infer_from_model_prefix(resolved_model)
    if prefix_info:
        suggestion["sources"].append("model_rules")
        merge_suggestion(suggestion, prefix_info, "model_rules", 0.7)
        if not suggestion.get("maker"):
            maker = detect_maker_from_text(resolved_model)
            merge_suggestion(suggestion, {"maker": maker}, "model_rules", 0.55)

    # --- 登録済みDBから類似商品 ---
    db_match = find_similar_product(resolved_model, products)
    if db_match:
        suggestion["sources"].append("database")
        suggestion["matched_product"] = {
            "id": db_match.get("id"),
            "maker": db_match.get("maker"),
            "product_name": db_match.get("product_name"),
            "model_number": db_match.get("model_number"),
            "category": db_match.get("category"),
            "tags": db_match.get("tags"),
            "memo": db_match.get("memo"),
            "score": db_match.get("_match_score"),
        }
        merge_suggestion(
            suggestion,
            {
                "maker": db_match.get("maker"),
                "product_name": db_match.get("product_name"),
                "category": db_match.get("category"),
                "tags": db_match.get("tags"),
            },
            "database",
            min(0.95, (db_match.get("_match_score") or 0) / 100),
        )

    # --- テキスト全体から再推論 ---
    joined = " ".join(texts)
    if joined:
        if not suggestion.get("maker"):
            merge_suggestion(
                suggestion,
                {"maker": detect_maker_from_text(joined)},
                "text",
                0.6,
            )
        if not suggestion.get("category"):
            merge_suggestion(
                suggestion,
                {"category": infer_category_from_text(joined)},
                "text",
                0.55,
            )
        if not suggestion.get("product_name") and suggestion.get("page_title"):
            merge_suggestion(
                suggestion,
                {"product_name": clean_product_title(suggestion["page_title"])},
                "text",
                0.5,
            )

    if not suggestion.get("model_candidates") and resolved_model:
        suggestion["model_candidates"] = extract_model_candidates(resolved_model)

    # 信頼度
    confidences = list(suggestion.get("_field_confidence", {}).values())
    if confidences:
        suggestion["confidence"] = round(sum(confidences) / len(confidences), 2)
    elif suggestion.get("model_number"):
        suggestion["confidence"] = 0.35

    suggestion["sources"] = list(dict.fromkeys(suggestion["sources"]))
    suggestion.pop("_field_sources", None)
    suggestion.pop("_field_confidence", None)

    if not suggestion.get("product_name") and suggestion.get("model_number"):
        suggestion["product_name"] = "未登録"

    return suggestion
