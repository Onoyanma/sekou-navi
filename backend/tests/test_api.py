"""API の結合テスト（重い AI モデルはスタブに置き換えて実行する）。"""

import io
import os
import shutil
import unittest

from tests.stubs import install_stubs, use_temporary_storage

STORAGE_ROOT = use_temporary_storage()
install_stubs()

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

import main  # noqa: E402

SAMPLE_PRODUCT = {
    "maker": "TOTO",
    "product_name": "トイレットペーパーホルダー",
    "model_number": "YH51R",
    "category": "トイレ",
    "memo": "テスト用",
    "tags": "",
    "manual_url": "",
    "install_url": "",
    "official_url": "",
}


def make_png_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), color=(200, 30, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def tearDownModule():
    shutil.rmtree(STORAGE_ROOT, ignore_errors=True)


class ProductApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def create_product(self, **overrides):
        payload = {**SAMPLE_PRODUCT, **overrides}
        response = self.client.post("/products", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["id"]

    def test_root(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("message", response.json())

    def test_create_get_update_delete(self):
        product_id = self.create_product()

        response = self.client.get(f"/products/{product_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["model_number"], "YH51R")

        updated = {**SAMPLE_PRODUCT, "product_name": "紙巻器"}
        response = self.client.put(f"/products/{product_id}", json=updated)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["product_name"], "紙巻器")

        response = self.client.delete(f"/products/{product_id}")
        self.assertEqual(response.status_code, 200)

        response = self.client.get(f"/products/{product_id}")
        self.assertEqual(response.status_code, 404)

    def test_missing_product_returns_404(self):
        self.assertEqual(self.client.get("/products/999999").status_code, 404)
        self.assertEqual(
            self.client.put("/products/999999", json=SAMPLE_PRODUCT).status_code,
            404,
        )
        self.assertEqual(self.client.delete("/products/999999").status_code, 404)

    def test_create_requires_fields(self):
        response = self.client.post("/products", json={"maker": "TOTO"})
        self.assertEqual(response.status_code, 422)

    def test_summary_counts_products(self):
        before = self.client.get("/products/summary").json()["count"]
        self.create_product(model_number="SUMMARY1")
        after = self.client.get("/products/summary?limit=3").json()

        self.assertEqual(after["count"], before + 1)
        self.assertLessEqual(len(after["recent"]), 3)

    def test_keyword_search_finds_by_model_number(self):
        self.create_product(model_number="THY582N", product_name="排水金具")

        response = self.client.get("/ai-search", params={"q": "THY582N", "mode": "keyword"})
        self.assertEqual(response.status_code, 200, response.text)

        models = [item["product"]["model_number"] for item in response.json()["results"]]
        self.assertIn("THY582N", models)

    def test_hybrid_search_returns_json_without_embeddings(self):
        # 埋め込みベクトル（バイナリ）がレスポンスに混ざると JSON 変換で落ちる不具合の再発防止
        self.create_product(model_number="HYB100", product_name="洗面化粧台")

        for mode in ("hybrid", "semantic", "keyword"):
            response = self.client.get("/ai-search", params={"q": "HYB100", "mode": mode})
            self.assertEqual(response.status_code, 200, f"{mode}: {response.text}")
            for item in response.json()["results"]:
                self.assertNotIn("text_embedding", item["product"])

    def test_search_rejects_unknown_mode(self):
        response = self.client.get("/ai-search", params={"q": "x", "mode": "bad"})
        self.assertEqual(response.status_code, 400)

    def test_barcode_search_matches_model(self):
        self.create_product(model_number="KM5021", product_name="混合水栓")

        response = self.client.get("/barcode-search", params={"code": "KM5021"})
        self.assertEqual(response.status_code, 200, response.text)

        models = [item["product"]["model_number"] for item in response.json()["results"]]
        self.assertIn("KM5021", models)

    def test_image_upload_uses_safe_filename_and_is_removed_on_delete(self):
        product_id = self.create_product(model_number="IMG001")

        response = self.client.post(
            f"/products/{product_id}/images",
            files={"file": ("../../evil name.png", make_png_bytes(), "image/png")},
        )
        self.assertEqual(response.status_code, 200, response.text)

        images = self.client.get(f"/products/{product_id}/images").json()
        self.assertEqual(len(images), 1)

        stored_name = os.path.basename(images[0]["image_path"])
        self.assertNotIn("..", images[0]["image_path"])
        self.assertTrue(stored_name.endswith("evil_name.png"))

        stored_file = os.path.join(main.IMAGE_DIR, stored_name)
        self.assertTrue(os.path.exists(stored_file))

        self.client.delete(f"/products/{product_id}")
        self.assertFalse(os.path.exists(stored_file))


if __name__ == "__main__":
    unittest.main()
