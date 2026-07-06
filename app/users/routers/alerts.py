import logging
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.telegram import send_telegram_message
from app.users.models.alert import Alert
from app.users.models.user import User
from app.users.models.user_product import UserProduct
from app.users.schemas.alert import AlertCreate, AlertRead

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["alerts"])


async def _get_user_product(user_id: int, product_id: int, db: AsyncSession) -> UserProduct:
    result = await db.execute(
        select(UserProduct).where(
            UserProduct.user_id == user_id,
            UserProduct.product_id == product_id,
        )
    )
    user_product = result.scalar_one_or_none()
    if not user_product:
        raise HTTPException(status_code=404, detail="User is not tracking this product")
    return user_product


@router.post(
    "/{user_id}/products/{product_id}/alerts",
    response_model=AlertRead,
    status_code=201,
)
async def create_alert(
    user_id: int, product_id: int, data: AlertCreate, db: AsyncSession = Depends(get_db)
):
    user_product = await _get_user_product(user_id, product_id, db)

    alert = Alert(user_product_id=user_product.id, **data.model_dump())
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    logger.info(
        "Created alert id=%d for user_product_id=%d condition=%s threshold=%s",
        alert.id, user_product.id, alert.condition, alert.threshold,
    )
    return alert


@router.get(
    "/{user_id}/products/{product_id}/alerts",
    response_model=list[AlertRead],
)
async def list_alerts(user_id: int, product_id: int, db: AsyncSession = Depends(get_db)):
    user_product = await _get_user_product(user_id, product_id, db)
    result = await db.execute(
        select(Alert).where(Alert.user_product_id == user_product.id)
    )
    return result.scalars().all()


def _condition_met(
    condition: str,
    threshold: Decimal,
    previous_price: Decimal | None,
    new_price: Decimal,
) -> bool:
    if condition == "price_below":
        return new_price <= threshold
    if condition == "percent_drop":
        if previous_price is None or previous_price == 0:
            return False
        drop_pct = (previous_price - new_price) / previous_price * 100
        return drop_pct >= threshold
    return False


async def evaluate_alerts(
    product_id: int,
    previous_price: Decimal | None,
    new_price: Decimal,
    db: AsyncSession,
) -> None:
    """Evalúa las alertas activas de un producto tras registrarse un precio nuevo.

    'percent_drop' compara contra el precio inmediatamente anterior, no contra
    el mínimo histórico ni el primer precio registrado — es lo más simple y lo
    más intuitivo para "avisame si bajó de precio ahora".
    """
    result = await db.execute(
        select(Alert, UserProduct, User)
        .join(UserProduct, Alert.user_product_id == UserProduct.id)
        .join(User, UserProduct.user_id == User.id)
        .where(
            UserProduct.product_id == product_id,
            Alert.triggered_at.is_(None),
        )
    )
    rows = result.all()

    for alert, user_product, user in rows:
        if not _condition_met(alert.condition, alert.threshold, previous_price, new_price):
            continue

        alert.triggered_at = datetime.now(timezone.utc)
        db.add(alert)

        if user.telegram_id is not None:
            try:
                await send_telegram_message(
                    user.telegram_id,
                    f"Alerta disparada: el producto bajó a ${new_price}.",
                )
            except Exception:
                logger.exception(
                    "Fallo al enviar mensaje de Telegram a telegram_id=%s", user.telegram_id
                )

    await db.commit()
