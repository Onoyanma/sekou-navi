"""OCR で読んだ文字列から、型番の候補・メーカー・商品名のヒントを取り出す。"""

import re


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


# 型番ではない「電気仕様・寸法」の表記（980W、50/60Hz、455mm など）
SPEC_PATTERN = re.compile(
    r"^\d+(\.\d+)?(W|V|HZ|MHZ|MM|CM|KW|KG|A|L|ML|C)?"
    r"(/\d+(\.\d+)?(W|V|HZ|MHZ|MM|CM|KW|KG|A|L|ML|C)?)*$"
)

# 型番の近くに書かれているラベル語（同じ行の候補を優先する）
MODEL_LABEL_WORDS = ("型番", "品番", "形名", "形式", "型式", "MODEL")

# 先頭に置くほど優先して入れ替え候補にする（0 と O の取り違えが最も多い）
CONFUSABLE_REPLACEMENTS = {
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
    "2": ["Z"],
}

MAX_VARIANTS_PER_CANDIDATE = 4


def fix_digit_context_letter_o(text):
    """数字に挟まれた（または数字の直前/直後の）英字 O は 0 の誤読とみなして直す。

    例: SL-O13BK -> SL-013BK。I/L/S などは L50 や V28 のように正しい英字が
    数字の前に来ることが多く、機械的に直すと誤りが増えるので対象にしない。
    """
    chars = list(text)

    for i, char in enumerate(chars):
        if char != "O":
            continue

        left = chars[i - 1] if i > 0 else ""
        right = chars[i + 1] if i + 1 < len(chars) else ""

        left_ok = left == "" or left == "-" or left.isdigit()
        right_ok = right == "" or right == "-" or right.isdigit()
        has_digit_neighbor = left.isdigit() or right.isdigit()

        if left_ok and right_ok and has_digit_neighbor:
            chars[i] = "0"

    return "".join(chars)


def generate_ocr_variants(text):
    variants = [text]

    for i, char in enumerate(text):
        for replacement in CONFUSABLE_REPLACEMENTS.get(char.upper(), []):
            variant = text[:i] + replacement + text[i + 1:]
            if variant not in variants:
                variants.append(variant)

    return variants[: MAX_VARIANTS_PER_CANDIDATE + 1]


def score_model_candidate(match, line):
    score = 0

    has_alpha = any(c.isalpha() for c in match)
    has_digit = any(c.isdigit() for c in match)
    digit_count = sum(c.isdigit() for c in match)
    alpha_count = sum(c.isalpha() for c in match)

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

    if digit_count >= 2:
        score += 10

    if alpha_count >= 2:
        score += 5

    # 型番は英字で始まることが多く、数字始まりは寸法・製造番号であることが多い
    if match[0].isalpha():
        score += 15
    else:
        score -= 20

    # ハイフンなしの長い英数字列は製造番号などの可能性が高い
    if "-" not in match and len(match) > 10:
        score -= 15

    # 英字ばかりでハイフンもない文字列は、日本語の誤読ノイズであることが多い
    if "-" not in match and digit_count <= 2 and alpha_count >= 6:
        score -= 15

    if any(word in line.upper() for word in MODEL_LABEL_WORDS):
        score += 25

    return score


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
            match = match.strip(".,:;()[]{}<>-/")
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

            if SPEC_PATTERN.match(upper_match):
                continue

            # 英字を含まない数字とハイフンだけの文字列は、電話番号・製造番号であって型番ではない
            if not any(c.isalpha() for c in upper_match):
                continue

            upper_match = fix_digit_context_letter_o(upper_match)
            base_score = score_model_candidate(upper_match, text)

            for index, variant in enumerate(generate_ocr_variants(upper_match)):
                variant_score = max(0, base_score - (10 if index else 0))

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
    "SHARP": ["SHARP", "シャープ"],
    "Paloma": ["PALOMA", "パロマ"],
    "アイホン": ["AIPHONE", "アイホン"],
    "アイリスオーヤマ": ["IRIS OHYAMA", "IRISOHYAMA", "アイリスオーヤマ"],
    "東芝": ["TOSHIBA", "東芝"],
    "ダイキン": ["DAIKIN", "ダイキン"],
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
