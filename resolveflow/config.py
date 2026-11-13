from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./resolveflow.db"
    jwt_secret: str = "local-development-secret-change-me"
    jwt_expire_minutes: int = 60
    demo_username: str = "demo"
    demo_password: str = "change-this-password"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"


settings = Settings()
