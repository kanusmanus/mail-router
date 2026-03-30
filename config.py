"""
Configuratie voor Mail Router applicatie.
Alle waarden worden geladen vanuit environment variables of .env bestand.
"""
from pydantic_settings import BaseSettings
from typing import Dict


class Settings(BaseSettings):
    """Application settings geladen vanuit environment variables"""

    # Azure AD
    azure_client_id: str
    azure_client_secret: str
    azure_tenant_id: str = "common"

    # Anthropic
    anthropic_api_key: str

    # Application
    webhook_url: str                  # bijv. https://mail-router.jouwdomein.nl
    mailbox_email: str                # te monitoren mailbox
    service_account_email: str
    service_account_password: str
    environment: str = "production"

    # Webhook beveiliging
    webhook_client_state: str = "mail-router-secret"   # roteer dit regelmatig

    # Logging
    log_level: str = "INFO"

    # Department routing
    department_emails: Dict[str, str] = {
        "Customer Support": "customersupport@ifcnl.com",
        "Douane": "douane@ifcnl.com",
        "Import": "import@ifcnl.com",
        "Transport": "transport@ifcnl.com",
        "Groupage": "groupage@ifcnl.com",
    }

    fallback_email: str = "fallback@ifcnl.com"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
