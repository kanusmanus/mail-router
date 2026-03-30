"""
Gedeelde authenticatie factory voor Microsoft Graph / O365.
Alle services die een Account nodig hebben, gebruiken deze functie.
"""
import logging
from O365 import Account
from config import settings

logger = logging.getLogger(__name__)


def get_authenticated_account() -> Account:
    """
    Maak en authenticeer een O365 Account via password flow.
    Gooit RuntimeError als authenticatie mislukt.
    """
    account = Account(
        settings.azure_client_id,
        auth_flow_type="password",
        tenant_id=settings.azure_tenant_id,
        main_resource=settings.mailbox_email,
        username=settings.service_account_email,
        password=settings.service_account_password,
    )

    if not account.authenticate(
        username=settings.service_account_email,
        password=settings.service_account_password,
    ):
        raise RuntimeError(
            f"Microsoft authenticatie mislukt voor {settings.service_account_email}"
        )

    logger.info(f"✓ Geauthenticeerd als {settings.service_account_email}")
    return account
