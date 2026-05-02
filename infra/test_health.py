#!/usr/bin/env python3
"""
=============================================================================
LinkAnvil — Script de Verificación de Salud
=============================================================================
Verifica que todos los servicios están disponibles y que pueden comunicarse
entre sí desde dentro de la red Docker (cerebro-net).

Uso:
  # Ejecutar directamente (requiere Python 3.9+):
  python infra/test_health.py

  # O via Docker (sin dependencias locales):
  docker run --rm --network cerebro-net python:3.12-slim \
    bash -c "pip install requests psycopg2-binary pika redis -q && python /test.py"
=============================================================================
"""

import sys
import time
import json
import socket
import urllib.request
import urllib.error
from typing import NamedTuple

# ─── Colores ANSI ─────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

class Result(NamedTuple):
    name: str
    ok: bool
    detail: str
    url: str = ""

# ─── Helpers ──────────────────────────────────────────────────────────────────

def http_get(url: str, timeout: int = 5, headers: dict = None) -> tuple[int, str]:
    """Hace GET y devuelve (status_code, body)"""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, str(e)
    except Exception as e:
        return 0, str(e)


def tcp_check(host: str, port: int, timeout: int = 5) -> bool:
    """Verifica que un puerto TCP está abierto"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def print_header(text: str):
    width = 72
    print(f"\n{BOLD}{CYAN}{'═' * width}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'═' * width}{RESET}")


def print_result(r: Result):
    icon  = f"{GREEN}✅" if r.ok else f"{RED}❌"
    name  = f"{BOLD}{r.name:<35}{RESET}"
    detail = f"{YELLOW}{r.detail}{RESET}" if not r.ok else r.detail
    url_str = f"  {BLUE}→ {r.url}{RESET}" if r.url else ""
    print(f"  {icon}  {name}  {detail}{url_str}")


# ─── Checks individuales ──────────────────────────────────────────────────────

def check_traefik() -> list[Result]:
    results = []
    # Dashboard API
    code, body = http_get("http://localhost:8080/api/rawdata")
    results.append(Result(
        "Traefik Dashboard API",
        code == 200,
        f"HTTP {code}" if code else "Sin conexión",
        "http://localhost:8080"
    ))
    # Health ping
    code2, _ = http_get("http://localhost:8080/ping")
    results.append(Result(
        "Traefik /ping",
        code2 == 200,
        f"HTTP {code2}" if code2 else "Sin conexión"
    ))
    return results


def check_rabbitmq() -> list[Result]:
    results = []
    # Management API
    import base64
    creds = base64.b64encode(b"cerebro:cerebro_pass").decode()
    code, body = http_get(
        "http://localhost:15672/api/overview",
        headers={"Authorization": f"Basic {creds}"}
    )
    ok = code == 200
    if ok:
        try:
            data = json.loads(body)
            detail = f"RabbitMQ {data.get('rabbitmq_version', '?')} — vhost: {data.get('vhost', '?')}"
        except Exception:
            detail = f"HTTP {code}"
    else:
        detail = f"HTTP {code}" if code else "Sin conexión"

    results.append(Result("RabbitMQ Management UI", ok, detail, "http://localhost:15672"))

    # AMQP port
    amqp_ok = tcp_check("localhost", 5672)
    results.append(Result("RabbitMQ AMQP  (port 5672)", amqp_ok, "Puerto abierto" if amqp_ok else "Puerto cerrado"))

    # Verificar colas definidas (DLQ, etc.)
    if ok:
        c2, b2 = http_get(
            "http://localhost:15672/api/queues/%2Fcerebro",
            headers={"Authorization": f"Basic {creds}"}
        )
        if c2 == 200:
            queues = json.loads(b2)
            queue_names = [q.get("name", "") for q in queues]
            expected = ["q.url.ingesta", "q.url.fallidas", "q.embeddings", "q.curador.nocturno"]
            missing = [q for q in expected if q not in queue_names]
            results.append(Result(
                "RabbitMQ Colas (DLQ, etc.)",
                len(missing) == 0,
                f"✓ {len(queue_names)} colas" if not missing else f"Falta: {missing}",
                "http://localhost:15672/#/queues"
            ))

    return results


def check_redis() -> list[Result]:
    # TCP check
    tcp_ok = tcp_check("localhost", 6379)
    results = [Result("Redis TCP (port 6379)", tcp_ok, "Puerto abierto" if tcp_ok else "Puerto cerrado")]

    # PING via redis-cli en Docker
    if tcp_ok:
        try:
            import subprocess
            r = subprocess.run(
                ["docker", "exec", "cerebro-redis", "redis-cli", "-a", "cerebro_redis_pass", "ping"],
                capture_output=True, text=True, timeout=5
            )
            pong = "PONG" in r.stdout
            results.append(Result("Redis PING", pong, "PONG ✓" if pong else f"Error: {r.stderr.strip()}"))
        except Exception as e:
            results.append(Result("Redis PING", False, f"Error: {e}"))

    return results


def check_postgres() -> list[Result]:
    tcp_ok = tcp_check("localhost", 5432)
    results = [Result("PostgreSQL TCP (port 5432)", tcp_ok, "Puerto abierto" if tcp_ok else "Puerto cerrado")]

    if tcp_ok:
        try:
            import subprocess
            r = subprocess.run(
                ["docker", "exec", "cerebro-postgres",
                 "psql", "-U", "cerebro", "-d", "cerebro_brain",
                 "-c", "SELECT COUNT(*) FROM recursos;"],
                capture_output=True, text=True, timeout=10
            )
            ok = r.returncode == 0
            detail = "Schema OK (tabla recursos existe)" if ok else r.stderr.strip()
            results.append(Result("PostgreSQL Schema (tabla recursos)", ok, detail))

            # Verificar outbox
            r2 = subprocess.run(
                ["docker", "exec", "cerebro-postgres",
                 "psql", "-U", "cerebro", "-d", "cerebro_brain",
                 "-c", "SELECT COUNT(*) FROM outbox_eventos;"],
                capture_output=True, text=True, timeout=10
            )
            ok2 = r2.returncode == 0
            results.append(Result("PostgreSQL Outbox Pattern", ok2, "tabla outbox_eventos OK" if ok2 else r2.stderr.strip()))
        except Exception as e:
            results.append(Result("PostgreSQL Schema", False, f"Error: {e}"))

    return results


def check_qdrant() -> list[Result]:
    code, body = http_get("http://localhost:6333/healthz")
    ok = code == 200
    results = [Result("Qdrant REST API /healthz", ok, f"HTTP {code}" if code else "Sin conexión", "http://localhost:6333")]

    if ok:
        c2, b2 = http_get("http://localhost:6333/collections")
        if c2 == 200:
            data = json.loads(b2)
            cols = data.get("result", {}).get("collections", [])
            results.append(Result("Qdrant Collections", True, f"{len(cols)} colecciones disponibles", "http://localhost:6333/dashboard"))

    # gRPC port
    grpc_ok = tcp_check("localhost", 6334)
    results.append(Result("Qdrant gRPC (port 6334)", grpc_ok, "Puerto abierto" if grpc_ok else "Puerto cerrado"))

    return results


def check_litellm() -> list[Result]:
    code, body = http_get("http://localhost:4000/health/readiness")
    ok = code == 200
    results = [Result("LiteLLM Gateway /health", ok, f"HTTP {code}" if code else "Sin conexión (normal sin API keys)", "http://localhost:4000")]

    # Verificar modelos disponibles
    import base64
    headers = {"Authorization": "Bearer sk-cerebro-master-key"}
    c2, b2 = http_get("http://localhost:4000/models", headers=headers)
    if c2 == 200:
        try:
            data = json.loads(b2)
            models = data.get("data", [])
            results.append(Result("LiteLLM Modelos configurados", True, f"{len(models)} modelos: {[m.get('id','?') for m in models[:3]]}"))
        except Exception:
            results.append(Result("LiteLLM Modelos configurados", c2 == 200, f"HTTP {c2}"))

    return results


def check_n8n() -> list[Result]:
    code, body = http_get("http://localhost:5678/healthz")
    ok = code == 200
    results = [Result("n8n Workflows /healthz", ok, f"HTTP {code}" if code else "Sin conexión (puede tardar 60s en arrancar)", "http://localhost:5678")]
    return results


def check_jaeger() -> list[Result]:
    code, _ = http_get("http://localhost:16686/")
    ok = code == 200
    results = [Result("Jaeger UI", ok, f"HTTP {code}" if code else "Sin conexión", "http://localhost:16686")]

    # Verificar API de servicios
    c2, b2 = http_get("http://localhost:16686/api/services")
    if c2 == 200:
        data = json.loads(b2)
        svcs = data.get("data", [])
        results.append(Result("Jaeger API /services", True, f"{len(svcs)} servicios registrados: {svcs[:3]}"))

    return results


def check_otel() -> list[Result]:
    # Health check extension
    code, _ = http_get("http://localhost:13133/healthz")
    ok = code == 200
    results = [Result("OTel Collector /healthz", ok, f"HTTP {code}" if code else "Sin conexión")]

    # gRPC port
    grpc_ok = tcp_check("localhost", 4317)
    results.append(Result("OTel OTLP gRPC (port 4317)", grpc_ok, "Puerto abierto" if grpc_ok else "Puerto cerrado"))

    # HTTP port
    http_ok = tcp_check("localhost", 4318)
    results.append(Result("OTel OTLP HTTP (port 4318)", http_ok, "Puerto abierto" if http_ok else "Puerto cerrado"))

    return results


def check_prometheus() -> list[Result]:
    code, body = http_get("http://localhost:9090/-/healthy")
    ok = code == 200
    results = [Result("Prometheus /healthy", ok, f"HTTP {code}" if code else "Sin conexión", "http://localhost:9090")]

    # Verificar targets
    c2, b2 = http_get("http://localhost:9090/api/v1/targets")
    if c2 == 200:
        data = json.loads(b2)
        active = data.get("data", {}).get("activeTargets", [])
        up = sum(1 for t in active if t.get("health") == "up")
        results.append(Result(
            "Prometheus Targets UP",
            up > 0,
            f"{up}/{len(active)} targets healthy",
            "http://localhost:9090/targets"
        ))

    return results


def check_grafana() -> list[Result]:
    code, body = http_get("http://localhost:3000/api/health")
    ok = code == 200
    if ok:
        try:
            data = json.loads(body)
            detail = f"Grafana {data.get('version', '?')} — DB: {data.get('database', '?')}"
        except Exception:
            detail = f"HTTP {code}"
    else:
        detail = f"HTTP {code}" if code else "Sin conexión"
    results = [Result("Grafana Dashboard", ok, detail, "http://localhost:3000")]
    return results


def check_inter_service_connectivity() -> list[Result]:
    """Verifica conectividad INTRA-red usando docker exec"""
    results = []
    import subprocess

    tests = [
        # (desde_container, hacia_servicio, puerto, descripción)
        ("cerebro-n8n",        "postgres",         "5432", "n8n → PostgreSQL"),
        ("cerebro-n8n",        "redis",             "6379", "n8n → Redis"),
        ("cerebro-n8n",        "rabbitmq",          "5672", "n8n → RabbitMQ"),
        ("cerebro-litellm",    "postgres",          "5432", "LiteLLM → PostgreSQL"),
        ("cerebro-litellm",    "redis",             "6379", "LiteLLM → Redis (caché)"),
        ("cerebro-traefik",    "n8n",               "5678", "Traefik → n8n"),
        ("cerebro-traefik",    "litellm",           "4000", "Traefik → LiteLLM"),
        ("cerebro-otel",       "jaeger",            "4317", "OTel → Jaeger gRPC"),
        ("cerebro-prometheus", "redis-exporter",    "9121", "Prometheus → Redis Exporter"),
        ("cerebro-prometheus", "rabbitmq-exporter", "9419", "Prometheus → RabbitMQ Exporter"),
        ("cerebro-prometheus", "postgres-exporter", "9187", "Prometheus → PG Exporter"),
        ("cerebro-grafana",    "prometheus",        "9090", "Grafana → Prometheus"),
        ("cerebro-grafana",    "jaeger",            "16686","Grafana → Jaeger"),
    ]

    for container, target_host, target_port, desc in tests:
        try:
            r = subprocess.run(
                ["docker", "exec", container,
                 "sh", "-c", f"nc -zw3 {target_host} {target_port} && echo OK || echo FAIL"],
                capture_output=True, text=True, timeout=10
            )
            ok = "OK" in r.stdout
            results.append(Result(
                f"Red: {desc}",
                ok,
                "✓ Conectado" if ok else f"✗ Sin ruta ({r.stderr.strip() or r.stdout.strip()})"
            ))
        except subprocess.TimeoutExpired:
            results.append(Result(f"Red: {desc}", False, "Timeout"))
        except Exception as e:
            results.append(Result(f"Red: {desc}", False, f"Error: {e}"))

    return results


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    print(f"\n{BOLD}{'🧠 LinkAnvil':^72}{RESET}")
    print(f"{'Verificación de Salud de la Infraestructura':^72}")
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S'):^72}\n")

    all_results: list[Result] = []

    sections = [
        ("🔀  API GATEWAY — Traefik",           check_traefik),
        ("📨  MESSAGE BUS — RabbitMQ",           check_rabbitmq),
        ("⚡  CACHÉ — Redis",                   check_redis),
        ("🗄️  BASE DE DATOS — PostgreSQL",      check_postgres),
        ("🧠  VECTOR DB — Qdrant",              check_qdrant),
        ("🤖  LLM GATEWAY — LiteLLM",           check_litellm),
        ("🔄  ORQUESTADOR — n8n",               check_n8n),
        ("🔭  TRACING — Jaeger",                check_jaeger),
        ("📡  OTEL COLLECTOR",                  check_otel),
        ("📊  MÉTRICAS — Prometheus",           check_prometheus),
        ("📈  DASHBOARDS — Grafana",            check_grafana),
    ]

    for title, fn in sections:
        print_header(title)
        try:
            results = fn()
            for r in results:
                print_result(r)
                all_results.append(r)
        except Exception as e:
            err = Result(title, False, f"Error inesperado: {e}")
            print_result(err)
            all_results.append(err)

    # Conectividad inter-servicio
    print_header("🌐  CONECTIVIDAD INTER-SERVICIO (cerebro-net)")
    inter = check_inter_service_connectivity()
    for r in inter:
        print_result(r)
        all_results.append(r)

    # ─── Resumen final ────────────────────────────────────────────────────────
    total = len(all_results)
    passed = sum(1 for r in all_results if r.ok)
    failed = total - passed
    pct = int(passed / total * 100) if total else 0

    color = GREEN if pct == 100 else (YELLOW if pct >= 70 else RED)

    print(f"\n{BOLD}{'─' * 72}{RESET}")
    print(f"{BOLD}  📊 RESUMEN FINAL{RESET}")
    print(f"{'─' * 72}")
    print(f"  Total checks :  {total}")
    print(f"  {GREEN}Pasados       :  {passed}{RESET}")
    if failed:
        print(f"  {RED}Fallidos      :  {failed}{RESET}")
    print(f"  {color}Porcentaje    :  {pct}%{RESET}")
    print(f"{'─' * 72}\n")

    if failed:
        print(f"{RED}{BOLD}  ⚠️  Algunos servicios necesitan atención:{RESET}")
        for r in all_results:
            if not r.ok:
                print(f"     • {r.name}: {r.detail}")
        print()

    if pct == 100:
        print(f"  {GREEN}{BOLD}🎉 Infraestructura 100% operativa!{RESET}\n")
    
    print("  🔗 URLs de acceso:")
    print("     Traefik Dashboard : http://localhost:8080")
    print("     RabbitMQ UI       : http://localhost:15672  (cerebro / cerebro_pass)")
    print("     n8n Workflows     : http://localhost:5678   (admin / cerebro_n8n_pass)")
    print("     Grafana           : http://localhost:3000   (admin / cerebro_grafana_pass)")
    print("     Prometheus        : http://localhost:9090")
    print("     Jaeger Tracing    : http://localhost:16686")
    print("     LiteLLM Gateway   : http://localhost:4000")
    print("     Qdrant Vector DB  : http://localhost:6333/dashboard")
    print()

    sys.exit(0 if pct >= 70 else 1)


if __name__ == "__main__":
    main()
