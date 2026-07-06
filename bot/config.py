from pydantic_settings import BaseSettings


class BotSettings(BaseSettings):
    TELEGRAM_BOT_TOKEN: str
    API_BASE_URL: str = "http://localhost:8000"
    API_TIMEOUT: float = 10.0
    LOG_LEVEL: str = "INFO"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = BotSettings()
