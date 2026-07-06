from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class AlertBase(BaseModel):
    condition: Literal["percent_drop", "price_below"]
    threshold: Decimal


class AlertCreate(AlertBase):
    pass


class AlertRead(AlertBase):
    id: int
    user_product_id: int
    triggered_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
