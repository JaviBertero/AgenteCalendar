import asyncio
import logging
import re
import socket

logger = logging.getLogger(__name__)

DUMMY_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
    "test.com",
    "domain.com",
    "sample.com",
    "email.com",
    "invalid.com",
    "localhost",
}

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def is_valid_email_syntax(email: str | None) -> bool:
    """Verifica que la dirección de correo tenga una sintaxis estándar válida."""
    if not email or len(email) > 254:
        return False
    return bool(EMAIL_REGEX.match(email.strip()))


async def verify_email_domain_exists(email: str | None) -> bool:
    """
    Verifica que el correo tenga sintaxis válida, no use dominios ficticios
    y que su dominio realmente exista en DNS (resolución de host).
    """
    if not email or not is_valid_email_syntax(email):
        return False

    clean_email = email.strip().lower()
    domain = clean_email.split("@")[-1]

    if domain in DUMMY_DOMAINS:
        return False

    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, socket.gethostbyname, domain)
        return True
    except Exception as e:
        logger.warning("Verificación de email fallida. El dominio '%s' no existe en DNS: %s", domain, e)
        return False
