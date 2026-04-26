import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt


def _read_secret(env_name: str, file_env_suffix: str = "_FILE", default: Optional[str] = None) -> Optional[str]:
    """Read a secret from <env>_FILE, then <env>, then default."""
    file_path = os.getenv(env_name + file_env_suffix)
    if file_path and os.path.exists(file_path):
        with open(file_path) as f:
            return f.read().strip()
    return os.getenv(env_name, default)


SECRET_KEY = _read_secret("JWT_SECRET", default="cerebro_jwt_dev_secret_CHANGE_ME")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

# Cookie names — httpOnly for the session token, NOT-httpOnly for CSRF
# so the JS layer can read it and echo it back as a header.
SESSION_COOKIE = "cerebro_session"
CSRF_COOKIE = "cerebro_csrf"
CSRF_HEADER = "X-CSRF-Token"


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise ValueError("Token inválido o expirado")
