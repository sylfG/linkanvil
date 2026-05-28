"""Validacion anti-SSRF de URLs.

Bloquea schemes no-HTTP, hosts privados (RFC1918, loopback, link-local,
multicast, reserved), nombres internos del cluster Docker y .localhost.
Util tanto en el endpoint /ingest como en el scraper antes de hacer fetch
(p.ej. tras seguir un redirect).
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


ALLOWED_SCHEMES = {"http", "https"}

# Sufijos de hostname considerados internos al cluster. Cualquier match aqui
# se rechaza aunque la resolucion DNS apunte a una IP publica.
INTERNAL_HOSTNAME_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".cluster.local",
    ".docker",
    ".compose",
)

# Hostnames literales de servicios internos del compose. Cualquier coincidencia
# es rechazada para evitar SSRF a la API admin, Postgres, Redis, etc.
INTERNAL_HOSTNAMES = {
    "localhost",
    "cerebro-api",
    "cerebro-ingestion",
    "cerebro-web",
    "cerebro-scraper",
    "cerebro-embedder",
    "cerebro-outbox",
    "cerebro-notifier",
    "cerebro-litellm",
    "cerebro-postgres",
    "cerebro-redis",
    "cerebro-rabbitmq",
    "cerebro-qdrant",
    "cerebro-grafana",
    "cerebro-prometheus",
    "cerebro-jaeger",
    "cerebro-otel",
    "cerebro-n8n",
    "cerebro-traefik",
    "postgres",
    "redis",
    "rabbitmq",
    "qdrant",
    "litellm",
    "n8n",
    "grafana",
    "traefik",
    "jaeger",
    "otel",
}


class UnsafeURLError(ValueError):
    """URL rechazada por politica anti-SSRF."""


def validate_url(url: str, *, resolve_dns: bool = True) -> None:
    """Lanza UnsafeURLError si la URL apunta a un destino interno.

    Comprueba:
      1. Scheme en {http, https}.
      2. Hostname no es uno de los servicios internos del compose.
      3. Sufijos *.localhost / *.internal / etc.
      4. Si la URL ya contiene una IP literal, la comprueba contra
         redes privadas / loopback / link-local / reserved.
      5. Si resolve_dns=True (default), resuelve el hostname y verifica
         que TODAS las A/AAAA records apunten a IPs publicas. Esto
         tapa DNS rebinding y dominios externos que apuntan a 127.x.
    """
    if not url or not isinstance(url, str):
        raise UnsafeURLError("URL vacia o tipo invalido")

    try:
        parts = urlparse(url)
    except Exception as e:
        raise UnsafeURLError(f"URL malformada: {e}") from e

    scheme = (parts.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise UnsafeURLError(f"Scheme '{scheme}' no permitido (solo http/https)")

    host = (parts.hostname or "").lower().strip()
    if not host:
        raise UnsafeURLError("URL sin hostname")

    if host in INTERNAL_HOSTNAMES:
        raise UnsafeURLError(f"Hostname interno bloqueado: {host}")

    for suffix in INTERNAL_HOSTNAME_SUFFIXES:
        if host.endswith(suffix):
            raise UnsafeURLError(f"Sufijo de hostname interno bloqueado: {host}")

    # IP literal en el host?
    try:
        ip = ipaddress.ip_address(host)
        _check_ip(ip, original=host)
        return
    except ValueError:
        # No es IP literal; continuar con DNS resolution.
        pass

    if not resolve_dns:
        return

    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise UnsafeURLError(f"DNS resolution fallo para {host}: {e}") from e

    seen_any = False
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        seen_any = True
        _check_ip(ip, original=host)

    if not seen_any:
        raise UnsafeURLError(f"DNS sin records para {host}")


def _check_ip(ip: ipaddress._BaseAddress, *, original: str) -> None:
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        raise UnsafeURLError(
            f"IP privada/reservada bloqueada (host={original}, ip={ip})"
        )
