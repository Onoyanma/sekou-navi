"""評価スクリプトが使う、アプリの処理（OCR・型番抽出・照合）への入り口。

保存先の環境変数を設定したあとで呼ぶ必要があるため、import はこの関数の中で行う。
"""

from types import SimpleNamespace


def load_pipeline() -> SimpleNamespace:
    from services import embeddings, matching, model_numbers, ocr  # noqa: PLC0415

    return SimpleNamespace(
        extract_text_from_image=ocr.extract_text_from_image,
        extract_model_candidates=model_numbers.extract_model_candidates,
        detect_maker_from_text=model_numbers.detect_maker_from_text,
        extract_product_name_hints=model_numbers.extract_product_name_hints,
        find_similar_model_numbers=matching.find_similar_model_numbers,
        score_product_from_ocr=matching.score_product_from_ocr,
        product_row_to_result=matching.product_row_to_result,
        merge_similar_search_results=matching.merge_similar_search_results,
        normalize_embedding_vector=embeddings.normalize_embedding_vector,
        get_image_embedding=embeddings.get_image_embedding,
        MIN_SIMILARITY=matching.MIN_SIMILARITY,
    )


def set_image_baseline(value: float) -> None:
    """画像スコアの基準値を一時的に変える（基準値の比較実験用）。"""
    from services import matching  # noqa: PLC0415

    matching.IMAGE_SCORE_BASELINE = value
