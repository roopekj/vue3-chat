from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/chat"

    openai_base_url: str = "http://localhost:8000/v1"
    openai_api_key: str = "not-needed"
    model_name: str = "gpt-4o-mini"
    enable_thinking: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
