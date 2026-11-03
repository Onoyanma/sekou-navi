"""API のリクエスト本文の型。"""

from pydantic import BaseModel


class ProductCreate(BaseModel):
    maker: str
    product_name: str
    model_number: str
    category: str
    memo: str = ""
    tags: str = ""
    manual_url: str = ""
    install_url: str = ""
    official_url: str = ""


class ProductAutocompleteRequest(BaseModel):
    model_number: str = ""
    url: str = ""


class ProductUpdate(BaseModel):
    maker: str
    product_name: str
    model_number: str
    category: str
    memo: str = ""
    tags: str = ""
    manual_url: str = ""
    install_url: str = ""
    official_url: str = ""
