import functools
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from bot.api_client import ApiClient, ApiError
from bot.config import settings

logger = logging.getLogger(__name__)


# --- lifecycle ---

async def post_init(application: Application) -> None:
    application.bot_data["api"] = ApiClient(
        base_url=settings.API_BASE_URL,
        timeout=settings.API_TIMEOUT,
    )
    logger.info("API client ready (base_url=%s)", settings.API_BASE_URL)


async def post_shutdown(application: Application) -> None:
    api: ApiClient | None = application.bot_data.get("api")
    if api:
        await api.close()
        logger.info("API client closed.")


# --- error handler ---

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled exception", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "Ocurrió un error inesperado. Intentá de nuevo en un momento."
        )


# --- decorator ---

def require_user(handler):
    """Resolve telegram_id → internal user; short-circuit if the user is not registered."""
    @functools.wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        api: ApiClient = context.bot_data["api"]
        user = await api.get_user_by_telegram(update.effective_user.id)
        if user is None:
            await update.effective_message.reply_text(
                "No tenés una cuenta registrada. Contactá al administrador."
            )
            return
        return await handler(update, context, user)
    return wrapper


# --- helpers ---

async def resolve_product_id(api: ApiClient, user_id: int, position: int) -> int | None:
    """Traduce la posición mostrada por /list (1-indexed) al product_id real."""
    products = await api.get_user_products(user_id)
    if position < 1 or position > len(products):
        return None
    return products[position - 1]["id"]


# --- commands ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    api: ApiClient = context.bot_data["api"]
    telegram_id = update.effective_user.id
    user = await api.get_user_by_telegram(telegram_id)
    if user is None:
        tg_username = update.effective_user.username
        username = tg_username if tg_username else f"tg{telegram_id}"
        email = f"tg{telegram_id}@telegram.example.com"
        try:
            user = await api.create_user(username, email, telegram_id)
        except ApiError as e:
            if e.status_code == 409:
                user = await api.create_user(f"tg{telegram_id}", email, telegram_id)
            else:
                raise
        logger.info("Registered new user telegram_id=%d user_id=%s", telegram_id, user["id"])
    await update.message.reply_text("Hola, soy tu price tracker.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Comandos disponibles:\n"
        "/start — Iniciar el bot\n"
        "/help  — Mostrar esta ayuda\n"
        "/ping  — Verificar que el bot responde\n"
        "/track <url> — Trackear un producto\n"
        "/list — Ver tus productos trackeados\n"
        "/prices <n> — Ver historial de precios de un producto (usá el # de /list)\n"
        "/alerta <n> <condicion> <valor> — Avisar cuando price_below o percent_drop se cumpla"
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("pong")


@require_user
async def track(update: Update, context: ContextTypes.DEFAULT_TYPE, user: dict) -> None:
    api: ApiClient = context.bot_data["api"]
    url = " ".join(context.args).strip()
    if not url:
        await update.effective_message.reply_text("Uso: /track <url>")
        return
    if not url.startswith(("http://", "https://")):
        await update.effective_message.reply_text("La URL debe empezar con http:// o https://")
        return

    product = await api.find_product_by_url(url)
    if product is None:
        placeholder_name = url[:60]
        try:
            product = await api.create_product(placeholder_name, url)
        except ApiError as e:
            if e.status_code == 409:
                product = await api.find_product_by_url(url)
            else:
                raise

    try:
        await api.add_product_to_user(user["id"], product["id"])
    except ApiError as e:
        if e.status_code == 409:
            await update.effective_message.reply_text("Ya estabas trackeando este producto.")
            return
        raise

    await update.effective_message.reply_text(f"Producto agregado: {product['name']}")


@require_user
async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE, user: dict) -> None:
    api: ApiClient = context.bot_data["api"]
    products = await api.get_user_products(user["id"])

    if not products:
        await update.effective_message.reply_text(
            "Todavía no estás trackeando ningún producto. Usá /track <url> para empezar."
        )
        return

    lines = ["Tus productos trackeados:", ""]
    for position, p in enumerate(products, start=1):
        price = f"${p['last_price']}" if p["last_price"] is not None else "sin precio registrado"
        lines.append(f"#{position} — {p['name']}: {price}")
    lines.append("")
    lines.append("Usá /prices <n> para ver el historial de un producto.")

    await update.effective_message.reply_text("\n".join(lines))


@require_user
async def prices(update: Update, context: ContextTypes.DEFAULT_TYPE, user: dict) -> None:
    api: ApiClient = context.bot_data["api"]

    if not context.args:
        await update.effective_message.reply_text("Uso: /prices <n>")
        return
    try:
        position = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text(
            "Uso: /prices <n> (el número debe ser el # que ves en /list)"
        )
        return

    product_id = await resolve_product_id(api, user["id"], position)
    if product_id is None:
        await update.effective_message.reply_text(f"No tenés un producto #{position}. Usá /list.")
        return

    history = await api.get_price_history(product_id)
    if history is None:
        await update.effective_message.reply_text("Ese producto ya no existe.")
        return
    if not history:
        await update.effective_message.reply_text("Ese producto todavía no tiene precios registrados.")
        return

    history_asc = list(reversed(history))

    lines = ["Historial de precios:", ""]
    prev_price = None
    for record in history_asc:
        price = Decimal(record["price"])
        date_str = datetime.fromisoformat(record["recorded_at"]).strftime("%d/%m/%Y %H:%M")
        if prev_price is None:
            lines.append(f"{date_str} — ${price}")
        else:
            diff = price - prev_price
            pct = (diff / prev_price * 100) if prev_price != 0 else Decimal(0)
            arrow = "↑" if diff > 0 else "↓" if diff < 0 else "→"
            lines.append(f"{date_str} — ${price} ({arrow} {pct:+.1f}%)")
        prev_price = price

    await update.effective_message.reply_text("\n".join(lines))


@require_user
async def create_alert_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user: dict) -> None:
    api: ApiClient = context.bot_data["api"]

    if len(context.args) < 3:
        await update.effective_message.reply_text(
            "Uso: /alerta <n> <condicion> <valor>\n"
            "Condiciones: price_below, percent_drop\n"
            "Ejemplo: /alerta 1 price_below 50000"
        )
        return

    try:
        position = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("El primer argumento debe ser un número (ver /list).")
        return

    condition = context.args[1]
    if condition not in ("price_below", "percent_drop"):
        await update.effective_message.reply_text("Condición inválida. Usá price_below o percent_drop.")
        return

    try:
        threshold = Decimal(context.args[2])
    except InvalidOperation:
        await update.effective_message.reply_text("El valor debe ser un número.")
        return

    product_id = await resolve_product_id(api, user["id"], position)
    if product_id is None:
        await update.effective_message.reply_text(f"No tenés un producto #{position}. Usá /list.")
        return

    try:
        await api.create_alert(user["id"], product_id, condition, str(threshold))
    except ApiError as e:
        if e.status_code == 404:
            await update.effective_message.reply_text("Ese producto ya no está en tu lista.")
            return
        raise

    await update.effective_message.reply_text("Alerta creada. Te avisaré cuando se cumpla.")


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("No entiendo ese comando. Usá /help.")


# --- entrypoint ---

def main() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    app = (
        Application.builder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("track", track))
    app.add_handler(CommandHandler("list", list_products))
    app.add_handler(CommandHandler("prices", prices))
    app.add_handler(CommandHandler("alerta", create_alert_command))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    logger.info("Bot iniciado.")
    app.run_polling()


if __name__ == "__main__":
    main()
