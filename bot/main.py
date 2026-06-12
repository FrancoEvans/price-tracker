import functools
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from bot.api_client import ApiClient
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


# --- commands ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Hola, soy tu price tracker.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Comandos disponibles:\n"
        "/start — Iniciar el bot\n"
        "/help  — Mostrar esta ayuda\n"
        "/ping  — Verificar que el bot responde"
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("pong")


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
    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    logger.info("Bot iniciado.")
    app.run_polling()


if __name__ == "__main__":
    main()
