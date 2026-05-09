#!/usr/bin/env python3
"""
Zero-touch provisioning script para n8n.
- Espera a que n8n inicie.
- Realiza el setup del owner (`/rest/owner/setup`) si la base de datos está limpia.
- De lo contrario, se loguea vía `/rest/login`.
- Valida la API Key actual; si es inválida, la regenera (`/rest/api-keys`).
- Guarda la nueva API Key en .env de manera segura.
- Importa y activa todos los workflows de infra/n8n/workflows.
"""
import os, sys, json, time, glob
import urllib.request, urllib.error

ENV_FILE         = os.environ.get("ENV_FILE",      "/app/.env")
N8N_URL          = os.environ.get("N8N_URL",       "http://n8n:5678")
N8N_USER         = os.environ.get("N8N_USER",      "admin")
N8N_PASS         = os.environ.get("N8N_PASSWORD",  "cerebro_n8n_pass")
WORKFLOWS_DIR    = os.environ.get("WORKFLOWS_DIR", "/app/infra/n8n/workflows")
KEY_LABEL        = "cerebro-mcp"
TIMEOUT          = 10


def load_env(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    res = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                res[k.strip()] = v.strip()
    return res


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


def wait_for_n8n():
    for _ in range(30):
        try:
            req = urllib.request.Request(f"{N8N_URL}/healthz")
            with urllib.request.urlopen(req, timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:
            pass
        time.sleep(2)
    print("ERROR: n8n no está respondiendo en /healthz", file=sys.stderr)
    sys.exit(1)


def get_n8n_cookie() -> str:
    """Intenta crear el owner o bien hacer login para obtener el n8n-auth."""
    email = f"{N8N_USER}@example.com"
    
    # 1. Intentar owner/setup (caso base de datos limpia)
    try:
        payload = {
            "email": email,
            "password": N8N_PASS,
            "firstName": "Admin",
            "lastName": "User"
        }
        req = urllib.request.Request(
            f"{N8N_URL}/rest/owner/setup",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            token = r.getheader("Set-Cookie")
            if token:
                print("✓ Owner n8n creado headlessly.")
                return token.split(";")[0]
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if "already setup" in body.lower() or e.code == 400:
            pass # Ya está configurado
        else:
            print(f"⚠ owner/setup error raro: {body}")
    
    # 2. Login normal
    try:
        req = urllib.request.Request(
            f"{N8N_URL}/rest/login",
            data=json.dumps({"emailOrLdapLoginId": email, "password": N8N_PASS}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            token = r.getheader("Set-Cookie")
            if token:
                print("✓ Login n8n exitoso.")
                return token.split(";")[0]
    except urllib.error.HTTPError as e:
        print(f"ERROR: Falló el login n8n: {e.read().decode()}", file=sys.stderr)
    except Exception as e:
        print(f"ERROR: Falló petición de login n8n: {e}", file=sys.stderr)
    
    return ""


def is_api_key_valid(api_key: str) -> bool:
    if not api_key: return False
    try:
        req = urllib.request.Request(f"{N8N_URL}/api/v1/workflows", headers={"X-N8N-API-KEY": api_key})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status == 200
    except Exception:
        return False


def ensure_api_key() -> str:
    env = load_env(ENV_FILE)
    existing_key = env.get("N8N_API_KEY", "").strip()

    if is_api_key_valid(existing_key):
        print("✓ N8N_API_KEY actual es válida.")
        return existing_key

    print("⚠ N8N_API_KEY inválida o faltante. Generando una nueva de forma headless...")
    cookie = get_n8n_cookie()
    if not cookie:
        print("ERROR: Imposible obtener auth cookie de n8n.", file=sys.stderr)
        sys.exit(1)

    try:
        payload = {
            "label": KEY_LABEL,
            "scopes": [
                "workflow:create", "workflow:read", "workflow:update", "workflow:delete", "workflow:list",
                "execution:read", "execution:list"
            ],
            "expiresAt": None
        }
        req = urllib.request.Request(
            f"{N8N_URL}/rest/api-keys",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Cookie": cookie},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            res = json.loads(r.read())
            new_key = res["data"]["rawApiKey"]
            write_env_key(ENV_FILE, "N8N_API_KEY", new_key)
            print(f"✓ Nueva N8N_API_KEY asignada exitosamente en .env")
            time.sleep(1) # propagación interna
            return new_key
    except Exception as e:
         print(f"ERROR: Fallo al crear la API_KEY interna: {e}", file=sys.stderr)
         if hasattr(e, 'read'): print(e.read().decode(), file=sys.stderr)
         sys.exit(1)


def import_workflows(api_key: str):
    # Obtener workflows ya existentes para no duplicar
    existing = {}
    try:
        req = urllib.request.Request(f"{N8N_URL}/api/v1/workflows", headers={"X-N8N-API-KEY": api_key})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read())
            existing = {w["name"]: w["id"] for w in data.get("data", [])}
    except Exception as e:
        print(f"⚠ Error al listar workflows previos: {e}")

    for file_path in glob.glob(os.path.join(WORKFLOWS_DIR, "*.json")):
        with open(file_path) as f: wf = json.load(f)
        name = wf.get("name", os.path.basename(file_path))
        
        if name in existing:
            print(f"  ✓ Workflow '{name}' ya existe, ignorando.")
            # WIP: Aquí podríamos hacer PUT /workflows/{id} si quisiéramos sobrescribir cambios locales
            continue
            
        print(f"  - Importando workflow: {name}...")
        
        # Eliminar 'active' para no romper el POST (es read-only al crear)
        active_status = wf.pop("active", False)
        wf.pop("tags", None)
        
        try:
            req = urllib.request.Request(
                f"{N8N_URL}/api/v1/workflows",
                data=json.dumps(wf).encode(),
                headers={"X-N8N-API-KEY": api_key, "Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                res = json.loads(r.read())
                new_id = res["id"]
            
            # Activar el workflow si lo requería la metadata JSON original
            if active_status:
                activate_req = urllib.request.Request(
                    f"{N8N_URL}/api/v1/workflows/{new_id}/activate",
                    
                    headers={"X-N8N-API-KEY": api_key, "Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(activate_req, timeout=TIMEOUT):
                    print(f"    ✓ Activado '{name}'.")
        except Exception as e:
            print(f"    ✗ Error al importar {name}: {e}")
            if hasattr(e, 'read'): print("     ", e.read().decode())

def main():
    print("Iniciando n8n headless bootstrap...")
    wait_for_n8n()
    
    global N8N_PASS
    if not N8N_PASS:
        env = load_env(ENV_FILE)
        N8N_PASS = env.get("N8N_PASSWORD", "cerebro_n8n_pass")

    api_key = ensure_api_key()
    import_workflows(api_key)
    
    print("\n✓ Bootstrap de n8n completado con éxito.")

if __name__ == "__main__":
    main()
