from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CPE_", extra="ignore")
    database_url: str = "sqlite:///./cpe.db"
    data_dir: Path = Path("./data")
    origin: str = "http://localhost:8097"
    secure_cookies: bool = False
    admin_email: str = "admin@cpe.local"
    admin_password: str = ""
    runtime_password: str = ""
    session_hours: int = 8
    max_upload_bytes: int = 8 * 1024**3
    max_expanded_bytes: int = 100 * 1024**3
    max_archive_files: int = 250000
    chunk_bytes: int = 8 * 1024**2
    max_record_bytes: int = 1024 * 1024
    recovery_days: int = 7
    llm_provider: str = "mock"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_api_key_file: str = ""
    llm_model: str = ""
    llm_allowed_hosts: str = ""
    llm_allow_http: bool = False
    llm_timeout: int = 90
    llm_context_tokens: int = 1000000
    llm_max_output_tokens: int = 4096
    oidc_issuer: str = ""
    oidc_audience: str = ""
    oidc_jwks_url: str = ""


settings = Settings()
