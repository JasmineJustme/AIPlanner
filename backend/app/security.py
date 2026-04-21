import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from app.config import settings
from app.utils.timezone import utc_now_naive


PBKDF2_ALGORITHM = "sha256"
PBKDF2_ITERATIONS = 120_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    ).hex()
    return f"pbkdf2_{PBKDF2_ALGORITHM}${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        method, iterations_str, salt, digest = stored_hash.split("$", 3)
        if not method.startswith("pbkdf2_"):
            return False
        algorithm = method.replace("pbkdf2_", "", 1)
        iterations = int(iterations_str)
    except (ValueError, TypeError):
        return False

    candidate = hashlib.pbkdf2_hmac(
        algorithm,
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return hmac.compare_digest(candidate, digest)


def generate_access_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    secret = settings.AUTH_TOKEN_SECRET or settings.ENCRYPTION_KEY
    return hashlib.sha256(f"{secret}:{token}".encode("utf-8")).hexdigest()


def token_expire_time() -> datetime:
    return utc_now_naive() + timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_HOURS)
