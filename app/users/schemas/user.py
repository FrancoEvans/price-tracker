from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    username: str
    email: EmailStr


class UserRead(BaseModel):
    id: int
    username: str
    email: str
    telegram_id: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
