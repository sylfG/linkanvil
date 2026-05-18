"""Cifrado simétrico de credenciales sensibles (LLM keys BYOK).

Se usa cryptography.Fernet (AES-128-CBC + HMAC-SHA256 + IV) — el estándar
canónico de la librería ``cryptography`` para tokens cifrados con clave
simétrica. Cada ciphertext incluye su propio IV y timestamp; rotación
futura puede leer el timestamp para forzar re-cifrado con clave nueva.

Inicialización
--------------
La clave maestra se lee de ``LLM_KEYS_ENCRYPTION_KEY`` al importar el
módulo. Si la env-var falta, el import falla rápido (RuntimeError) — es
preferible no arrancar que arrancar y filtrar plaintext.

Generación de una key nueva::

    python -c "from cryptography.fernet import Fernet; \\
               print(Fernet.generate_key().decode())"

Salida: 44 chars base64 url-safe (≡ 32 bytes). Pegar tal cual en .env.

Pérdida de la key = pérdida del acceso a TODAS las LLM keys cifradas
(los usuarios tendrían que rotar las suyas). Backup recomendado.
"""
from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken

_ENV_VAR = "LLM_KEYS_ENCRYPTION_KEY"
_raw = os.environ.get(_ENV_VAR)
if not _raw:
    raise RuntimeError(
        f"Missing env-var {_ENV_VAR}. Generate one with "
        '`python -c "from cryptography.fernet import Fernet; '
        'print(Fernet.generate_key().decode())"` and add it to '
        "your .env / docker-compose.yml."
    )

_fernet = Fernet(_raw.encode())


def encrypt_llm_key(plaintext: str) -> str:
    """Cifra una key BYOK para guardarla en BD. Devuelve string base64.

    No deduplica: dos llamadas con el mismo plaintext producen
    ciphertexts distintos (porque el IV cambia). Cualquiera de los dos
    descifra al mismo plaintext.
    """
    if not plaintext:
        raise ValueError("plaintext must be non-empty")
    return _fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_llm_key(ciphertext: str) -> str:
    """Descifra una key BYOK. Levanta InvalidToken si fue manipulado
    o si la clave maestra cambió.
    """
    if not ciphertext:
        raise ValueError("ciphertext must be non-empty")
    try:
        return _fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        # Re-raise con mensaje accionable, sin filtrar el ciphertext.
        raise InvalidToken(
            "Cannot decrypt LLM key — encryption key may have been "
            "rotated. User must re-configure their BYOK keys."
        ) from exc
