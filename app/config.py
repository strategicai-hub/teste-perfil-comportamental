import secrets

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    public_base_url: str = "http://localhost:8000/perfil-comportamental"
    database_url: str = "sqlite:///./data/app.db"

    gemini_api_key: str = ""

    google_credentials_json: str = ""
    google_sheet_id: str = ""

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = ""

    uazapi_base_url: str = ""
    uazapi_token: str = ""
    uazapi_instance: str = ""
    alert_phone: str = ""

    admin_user: str = ""
    admin_pass: str = ""
    jwt_secret: str = ""
    jwt_expire_hours: int = 24


settings = Settings()

if not settings.jwt_secret:
    settings.jwt_secret = secrets.token_hex(32)
