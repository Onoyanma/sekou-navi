import os
import sqlite3
import tempfile
import unittest

import database


def table_columns(db_path, table):
    conn = sqlite3.connect(db_path)
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


class InitDbTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "nested", "products.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_creates_all_tables_on_fresh_database(self):
        database.init_db(self.db_path)

        conn = sqlite3.connect(self.db_path)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        conn.close()

        self.assertTrue(
            {"products", "product_images", "ocr_history", "ai_feedback"} <= tables
        )
        self.assertTrue(
            {"tags", "image_embedding", "text_embedding"}
            <= table_columns(self.db_path, "products")
        )

    def test_is_idempotent(self):
        database.init_db(self.db_path)
        database.init_db(self.db_path)

    def test_adds_missing_columns_to_legacy_database(self):
        os.makedirs(os.path.dirname(self.db_path))
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "CREATE TABLE products (id INTEGER PRIMARY KEY, maker TEXT, memo TEXT)"
        )
        conn.execute("INSERT INTO products (maker, memo) VALUES ('TOTO', 'keep')")
        conn.commit()
        conn.close()

        database.init_db(self.db_path)

        columns = table_columns(self.db_path, "products")
        self.assertIn("tags", columns)
        self.assertIn("text_embedding", columns)

        conn = sqlite3.connect(self.db_path)
        memo = conn.execute("SELECT memo FROM products").fetchone()[0]
        conn.close()
        self.assertEqual(memo, "keep")


class SafeFilenameTest(unittest.TestCase):
    def test_strips_path_traversal(self):
        self.assertEqual(database.safe_filename("../../etc/passwd"), "passwd")
        self.assertEqual(database.safe_filename("..\\..\\win.ini"), "win.ini")

    def test_replaces_spaces_and_symbols(self):
        self.assertEqual(
            database.safe_filename("TOTO THY425-6R.jpg"), "TOTO_THY425-6R.jpg"
        )

    def test_keeps_japanese(self):
        self.assertEqual(database.safe_filename("型番ラベル.png"), "型番ラベル.png")

    def test_falls_back_to_default(self):
        self.assertEqual(database.safe_filename(""), "upload.jpg")
        self.assertEqual(database.safe_filename(None), "upload.jpg")
        self.assertEqual(database.safe_filename(".."), "upload.jpg")

    def test_unique_filename_has_prefix_and_differs(self):
        first = database.unique_filename("a.jpg", prefix="3_")
        second = database.unique_filename("a.jpg", prefix="3_")
        self.assertTrue(first.startswith("3_"))
        self.assertTrue(first.endswith("_a.jpg"))
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
