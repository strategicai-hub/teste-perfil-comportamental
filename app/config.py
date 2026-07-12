import secrets

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    public_base_url: str = "http://localhost:8000"
    base_path: str = ""
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
    # Super admin — login pela tela inicial. Só este e-mail entra no /admin.
    super_admin_email: str = "atendimento@strategicai.com.br"
    super_admin_password: str = ""
    jwt_secret: str = ""
    jwt_expire_hours: int = 24
    # Secure flag dos cookies. Se None, deriva de public_base_url (https → True).
    cookie_secure: bool | None = None


settings = Settings()

if not settings.jwt_secret:
    settings.jwt_secret = secrets.token_hex(32)

if settings.cookie_secure is None:
    settings.cookie_secure = settings.public_base_url.lower().startswith("https")
