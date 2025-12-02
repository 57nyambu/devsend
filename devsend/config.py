from pydantic_settings import BaseSettings
from typing import Optional
from pydantic import ConfigDict


class Settings(BaseSettings):
    # App settings
    secret_key: str = "dev-secret-key-change-in-production"
    debug: bool = True
    database_url: str = "sqlite:///./devsend.db"
    
    # Admin credentials
    admin_username: str = "admin"
    admin_password: str = "changeme"
    
    # Email settings
    default_sender_email: str = "noreply@example.com"
    default_sender_name: str = "DevSend"
    
    # Rate limiting
    max_emails_per_hour: int = 100
    
    # Logging
    log_level: str = "INFO"
    log_retention_days: int = 30
    
    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra='ignore'  # Ignore extra fields from .env
    )


settings = Settings()
