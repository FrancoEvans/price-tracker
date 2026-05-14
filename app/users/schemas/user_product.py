from datetime import datetime

from pydantic import BaseModel


class UserProductCreate(BaseModel):
    product_id: int


class UserProductRead(BaseModel):
    id: int
    user_id: int
    product_id: int
    added_at: datetime

    model_config = {"from_attributes": True}
