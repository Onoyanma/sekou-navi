"""写真から文字を読み取る（OCR）。画像をタイルに分け、英数字専用モデルと併用して小さい型番ラベルを読む。"""

import os

import easyocr
import numpy as np
from PIL import Image, ImageOps


_ocr_reader = None
_ocr_reader_en = None

# 型番ラベルは写真全体の中では小さい文字になるため、画像を重なりのあるタイルに分けて
# 読むと文字が大きく写り、読み取れる型番が増える（評価データで 5/14 → 8/14）。
OCR_MAX_SIDE = 1600
OCR_TILE_GRID = 3
OCR_TILE_OVERLAP = 0.25
OCR_MIN_CONFIDENCE = 0.3
OCR_DARK_TILE_MEAN = 100


def use_gpu_for_ocr():
    """GPU（CUDA / Apple の MPS）が使えるなら使う。SEKOU_OCR_GPU=0 で無効、1 で強制。

    CPU のみの環境（多くのクラウド）では従来どおり CPU で動く。
    Apple Silicon の MPS では、同じ写真で結果を変えずに処理時間が約 3 分の 1 になった。
    """
    setting = os.getenv("SEKOU_OCR_GPU", "").strip()
    if setting in ("0", "1"):
        return setting == "1"

    try:
        import torch  # noqa: PLC0415

        return bool(
            torch.cuda.is_available()
            or (getattr(torch.backends, "mps", None) and torch.backends.mps.is_available())
        )
    except Exception:
        return False


def get_ocr_reader():
    global _ocr_reader

    if _ocr_reader is None:
        _ocr_reader = easyocr.Reader(["en", "ja"], gpu=use_gpu_for_ocr())

    return _ocr_reader


def get_ocr_reader_en():
    """型番（英数字）専用。日本語モデルと混ぜないほうが英数字の誤読が少ない。"""
    global _ocr_reader_en

    if _ocr_reader_en is None:
        _ocr_reader_en = easyocr.Reader(["en"], gpu=use_gpu_for_ocr())

    return _ocr_reader_en


def load_image_for_ocr(image_path):
    image = ImageOps.exif_transpose(Image.open(image_path)).convert("RGB")

    longest = max(image.size)
    if longest > OCR_MAX_SIDE:
        ratio = OCR_MAX_SIDE / longest
        image = image.resize(
            (round(image.width * ratio), round(image.height * ratio))
        )

    return image


def split_into_tiles(image, grid=OCR_TILE_GRID, overlap=OCR_TILE_OVERLAP):
    width, height = image.size
    tile_w, tile_h = width / grid, height / grid
    tiles = []

    for row in range(grid):
        for col in range(grid):
            box = (
                max(0, int((col - overlap) * tile_w)),
                max(0, int((row - overlap) * tile_h)),
                min(width, int((col + 1 + overlap) * tile_w)),
                min(height, int((row + 1 + overlap) * tile_h)),
            )
            tiles.append(np.array(image.crop(box)))

    return tiles


def build_tile_inputs(image):
    """全体 + タイルを返す。暗いタイル（黒いラベルの白文字など）は白黒反転版も追加する。"""
    inputs = [np.array(image)]

    for tile in split_into_tiles(image):
        inputs.append(tile)
        if tile.mean() < OCR_DARK_TILE_MEAN:
            inputs.append(255 - tile)

    return inputs


def extract_text_from_image(image_path):
    """全体を日英モデルで、全体とタイルを英数字モデルで読み、重複を除いて返す。

    EasyOCR が低い確信度で返す断片は、背景や模様を文字と誤認したノイズが大半なので捨てる。
    """
    image = load_image_for_ocr(image_path)

    results = list(get_ocr_reader().readtext(np.array(image)))

    reader_en = get_ocr_reader_en()
    for tile in build_tile_inputs(image):
        results.extend(reader_en.readtext(tile))

    texts = [text for _, text, confidence in results if confidence >= OCR_MIN_CONFIDENCE]

    return list(dict.fromkeys(texts))
