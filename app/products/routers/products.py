import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.products.models.price import PriceRecord
from app.products.models.product import Product
from app.products.schemas.product import ProductCreate, ProductRead, ProductUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/products", tags=["products"])


async def _last_price(product_id: int, db: AsyncSession) -> None:
    result = await db.execute(
        select(PriceRecord.price)
        .where(PriceRecord.product_id == product_id)
        .order_by(desc(PriceRecord.recorded_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


@router.get("/", response_model=list[ProductRead])
async def list_products(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product))
    products = result.scalars().all()

    output = []
    for product in products:
        last_price = await _last_price(product.id, db)
        output.append(ProductRead.model_validate({**product.__dict__, "last_price": last_price}))
    return output


@router.post("/", response_model=ProductRead, status_code=201)
async def create_product(data: ProductCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Product).where(Product.url == data.url))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A product with this URL already exists")

    product = Product(**data.model_dump())
    db.add(product)
    await db.commit()
    await db.refresh(product)
    logger.info("Created product id=%d name=%r", product.id, product.name)
    return ProductRead.model_validate({**product.__dict__, "last_price": None})


@router.get("/{product_id}", response_model=ProductRead)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    last_price = await _last_price(product_id, db)
    return ProductRead.model_validate({**product.__dict__, "last_price": last_price})


@router.patch("/{product_id}", response_model=ProductRead)
async def update_product(
    product_id: int, data: ProductUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(product, field, value)

    await db.commit()
    await db.refresh(product)
    last_price = await _last_price(product_id, db)
    return ProductRead.model_validate({**product.__dict__, "last_price": last_price})


@router.delete("/{product_id}", status_code=204)
async def delete_product(product_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    await db.delete(product)
    await db.commit()
    logger.info("Deleted product id=%d", product_id)
