from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ProductBase(BaseModel):
    name: str
    url: str
    category: str | None = None


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    category: str | None = None


class ProductRead(ProductBase):
    id: int
    created_at: datetime
    last_price: Decimal | None = None

    model_config = {"from_attributes": True}
