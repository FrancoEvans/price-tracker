from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class PriceRecordCreate(BaseModel):
    price: Decimal
    currency: str = "ARS"


class PriceRecordRead(BaseModel):
    id: int
    product_id: int
    price: Decimal
    currency: str
    recorded_at: datetime

    model_config = {"from_attributes": True}
