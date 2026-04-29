#!/usr/bin/env python3
"""
Comprueba si N8N_API_KEY en .env es válida.
Si no existe o es inválida, genera una nueva y la escribe en .env.
Diseñado para ejecutarse como servicio efímero en docker compose.
"""
import os, sys, json, base64, time
import urllib.request, urllib.error

ENV_FILE   = os.environ.get("ENV_FILE",      "/app/.env")
N8N_URL    = os.environ.get("N8N_URL",       "http://n8n:5678")
N8N_USER   = os.environ.get("N8N_USER",      "admin")
N8N_PASS   = os.environ.get("N8N_PASSWORD",  "")
KEY_LABEL  = "claude-mcp"
TIMEOUT    = 10


# ---------------------------------------------------------------------------
# Helpers .env
# ---------------------------------------------------------------------------

def load_env(path: str) -> dict:
    result = {}
    if not os.path.exists(path):
        return result
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                result[k.strip()] = v.strip()
    return result


def write_env_key(path: str, key: str, value: str) -> None:
    lines = open(path).readlines() if os.path.exists(path) else []
    found = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}\n")
    with open(path, "w") as f:
        f.writelines(new_lines)


# ---------------------------------------------------------------------------
# HTTP básico contra la API de n8n
# ---------------------------------------------------------------------------

def _auth_header() -> str:
    creds = base64.b64encode(f"{N8N_USER}:{N8N_PASS}".encode()).decode()
    return f"Basic {creds}"


def n8n_call(method: str, path: str, body=None):
    req = urllib.request.Request(
        f"{N8N_URL}{path}",
        data=json.dumps(body).encode() if body else None,
        headers={"Authorization": _auth_header(), "Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def key_is_valid(api_key: str) -> bool:
    if not api_key:
        return False
    req = urllib.request.Request(
        f"{N8N_URL}/api/v1/workflows",
        headers={"X-N8N-API-KEY": api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Lógica principal
# ---------------------------------------------------------------------------

def main() -> None:
    global N8N_PASS

    env = load_env(ENV_FILE)

    if not N8N_PASS:
        N8N_PASS = env.get("N8N_PASSWORD", "")
    if not N8N_PASS:
        print("ERROR: N8N_PASSWORD no está definido.", file=sys.stderr)
        sys.exit(1)

    existing_key = env.get("N8N_API_KEY", "")

    if existing_key:
        print("N8N_API_KEY encontrada en .env, verificando validez…")
        if key_is_valid(existing_key):
            print("API key válida — nada que hacer.")
            return
        print("API key inválida o expirada, regenerando…")

    # Elimina keys previas con la misma etiqueta
    try:
        keys = n8n_call("GET", "/api/v1/api-key")
        for k in (keys if isinstance(keys, list) else []):
            if k.get("label") == KEY_LABEL:
                n8n_call("DELETE", f"/api/v1/api-key/{k['id']}")
                print(f"Key anterior eliminada (id: {k['id']})")
    except Exception as e:
        print(f"Aviso al limpiar keys anteriores: {e}")

    # Crea la nueva key
    result = n8n_call("POST", "/api/v1/api-key", {"label": KEY_LABEL})
    api_key = result.get("apiKey") or result.get("api_key", "")

    if not api_key:
        print(f"ERROR: respuesta inesperada de n8n: {result}", file=sys.stderr)
        sys.exit(1)

    write_env_key(ENV_FILE, "N8N_API_KEY", api_key)
    print(f"API key escrita en .env → N8N_API_KEY={api_key}")


if __name__ == "__main__":
    main()
