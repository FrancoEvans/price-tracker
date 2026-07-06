import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.products.models.product import Product
from app.products.routers.products import _last_price
from app.users.models.user import User
from app.users.models.user_product import UserProduct
from app.products.schemas.product import ProductRead
from app.users.schemas.user import UserCreate, UserRead
from app.users.schemas.user_product import UserProductCreate, UserProductRead

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["users"])


@router.get("/by-telegram/{telegram_id}", response_model=UserRead)
async def get_user_by_telegram(telegram_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/", response_model=UserRead, status_code=201)
async def create_user(data: UserCreate, db: AsyncSession = Depends(get_db)):
    conditions = [User.username == data.username, User.email == data.email]
    if data.telegram_id is not None:
        conditions.append(User.telegram_id == data.telegram_id)
    existing = await db.execute(select(User).where(or_(*conditions)))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username, email or telegram_id already exists")

    user = User(**data.model_dump())
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info("Created user id=%d username=%r", user.id, user.username)
    return user


@router.get("/{user_id}/products", response_model=list[ProductRead])
async def get_user_products(user_id: int, db: AsyncSession = Depends(get_db)):
    user = await db.execute(select(User).where(User.id == user_id))
    if not user.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="User not found")

    result = await db.execute(
        select(Product)
        .join(UserProduct, UserProduct.product_id == Product.id)
        .where(UserProduct.user_id == user_id)
        .order_by(UserProduct.id)
    )
    products = result.scalars().all()

    output = []
    for product in products:
        last_price = await _last_price(product.id, db)
        output.append(ProductRead.model_validate({**product.__dict__, "last_price": last_price}))
    return output


@router.post("/{user_id}/products", response_model=UserProductRead, status_code=201)
async def add_product_to_user(
    user_id: int, data: UserProductCreate, db: AsyncSession = Depends(get_db)
):
    user = await db.execute(select(User).where(User.id == user_id))
    if not user.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="User not found")

    product = await db.execute(select(Product).where(Product.id == data.product_id))
    if not product.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Product not found")

    existing = await db.execute(
        select(UserProduct).where(
            UserProduct.user_id == user_id,
            UserProduct.product_id == data.product_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Product already added to this user")

    user_product = UserProduct(user_id=user_id, product_id=data.product_id)
    db.add(user_product)
    await db.commit()
    await db.refresh(user_product)
    logger.info("User id=%d added product id=%d", user_id, data.product_id)
    return user_product
