import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.products.models.price import PriceRecord
from app.products.models.product import Product
from app.products.routers.products import _last_price
from app.products.schemas.price import PriceRecordCreate, PriceRecordRead
from app.users.routers.alerts import evaluate_alerts

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/products", tags=["prices"])


@router.get("/{product_id}/prices", response_model=list[PriceRecordRead])
async def get_price_history(product_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.id == product_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Product not found")

    records = await db.execute(
        select(PriceRecord)
        .where(PriceRecord.product_id == product_id)
        .order_by(PriceRecord.recorded_at.desc())
    )
    return records.scalars().all()


@router.post("/{product_id}/prices", response_model=PriceRecordRead, status_code=201)
async def record_price(
    product_id: int, data: PriceRecordCreate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Product not found")

    previous_price = await _last_price(product_id, db)

    record = PriceRecord(product_id=product_id, **data.model_dump())
    db.add(record)
    await db.commit()
    await db.refresh(record)
    logger.info("Recorded price %.2f %s for product id=%d", record.price, record.currency, product_id)

    try:
        await evaluate_alerts(product_id, previous_price, record.price, db)
    except Exception:
        # el precio ya se guardó y commiteó: un fallo evaluando/notificando alertas
        # (ej. Telegram caído) no debe hacer fallar el registro del precio en sí
        logger.exception("Error evaluando alertas para product_id=%d", product_id)

    return record
