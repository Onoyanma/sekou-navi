"""施工ナビ API のエントリーポイント。アプリの組み立てだけを行い、処理は routers/ と services/ に置く。"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from database import IMAGE_DIR, ensure_storage_dirs, init_db
from routers import autocomplete, products, recognition, search
from services.embeddings import (
    rebuild_missing_image_embeddings,
    rebuild_missing_product_text_embeddings,
)

app = FastAPI(title="施工ナビ API")

# 初回起動時（DB・画像フォルダがまだ無い場合）でも動くように先に用意する
ensure_storage_dirs()
init_db()

app.mount(
    "/images",
    StaticFiles(directory=IMAGE_DIR),
    name="images"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.environ.get(
            "SEKOU_CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 同じパスに重なる経路（/products/summary と /products/{id} など）は products の中で順序を保っている
app.include_router(products.router)
app.include_router(recognition.router)
app.include_router(autocomplete.router)
app.include_router(search.router)


@app.get("/")
def root():
    return {"message": "施工ナビ API"}


@app.on_event("startup")
def startup_rebuild_embeddings():
    try:
        updated_images = rebuild_missing_image_embeddings()
        if updated_images:
            print(f"Rebuilt {updated_images} image embeddings")

        updated_text = rebuild_missing_product_text_embeddings()
        if updated_text:
            print(f"Rebuilt {updated_text} product text embeddings")
    except Exception as e:
        print(f"embedding rebuild skipped: {e}")
