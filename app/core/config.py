from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    TELEGRAM_BOT_TOKEN: str

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
