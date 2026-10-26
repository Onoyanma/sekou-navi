"""重い機械学習ライブラリ（EasyOCR / SentenceTransformers）の代わりに使うテスト用スタブ。

テストではモデルのダウンロードや GPU を使わずに API の動作だけを確認したいので、
`main` を import する前に sys.modules に差し込む。
"""

import hashlib
import os
import sys
import tempfile
import types

import numpy as np


class _FakeReader:
    def __init__(self, *args, **kwargs):
        pass

    def readtext(self, *args, **kwargs):
        return []


class _FakeSentenceTransformer:
    """文字列や画像から、決まった 64 次元ベクトルを返すだけのモデル。"""

    def __init__(self, *args, **kwargs):
        pass

    def encode(self, value, normalize_embeddings=False, **kwargs):
        seed = hashlib.sha256(repr(value).encode("utf-8")).digest()
        rng = np.random.default_rng(int.from_bytes(seed[:8], "little"))
        vector = rng.standard_normal(64).astype(np.float32)
        if normalize_embeddings:
            vector /= np.linalg.norm(vector)
        return vector


def install_stubs():
    if "easyocr" not in sys.modules:
        module = types.ModuleType("easyocr")
        module.Reader = _FakeReader
        sys.modules["easyocr"] = module

    if "sentence_transformers" not in sys.modules:
        module = types.ModuleType("sentence_transformers")
        module.SentenceTransformer = _FakeSentenceTransformer
        sys.modules["sentence_transformers"] = module


def use_temporary_storage():
    """DB・画像の保存先を一時フォルダに向ける（本物のデータを汚さない）。"""
    root = tempfile.mkdtemp(prefix="sekou_navi_test_")
    os.environ["SEKOU_DB_PATH"] = os.path.join(root, "test.db")
    os.environ["SEKOU_IMAGE_DIR"] = os.path.join(root, "images")
    os.environ["SEKOU_TEMP_DIR"] = os.path.join(root, "temp_images")
    return root
