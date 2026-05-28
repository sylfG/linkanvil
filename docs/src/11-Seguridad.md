<div align="center">
  <img src="/logo-light.png" alt="Logo" width="80" height="80" class="light-only">
  <img src="/logo-dark.png" alt="Logo" width="80" height="80" class="dark-only">


# Seguridad — LinkAnvil

</div>

> Documento canónico de defense-in-depth de LinkAnvil. Describe las
> capas de seguridad implementadas en el código y la infraestructura,
> y la guía para desplegar nuevas instancias sin reintroducir agujeros.
>
> No incluye IPs, hostnames de despliegue ni claves; usa placeholders
> entre `<…>` para los valores específicos.

---

## Tabla de contenidos

1. [Modelo de amenazas](#1-modelo-de-amenazas)
2. [Capa de red — host](#2-capa-de-red--host)
3. [SSH](#3-ssh)
4. [Validación de URLs (anti-SSRF)](#4-validacion-de-urls-anti-ssrf)
5. [Hardening de containers](#5-hardening-de-containers)
6. [Security headers del frontend](#6-security-headers-del-frontend)
7. [Acceso público vía Tailscale Funnel](#7-acceso-publico-via-tailscale-funnel)
8. [Lo que no mitigamos](#8-lo-que-no-mitigamos)
9. [Checklist pre-deploy](#9-checklist-pre-deploy)
10. [Comandos de verificación post-deploy](#10-comandos-de-verificacion-post-deploy)

---

## 1. Modelo de amenazas

LinkAnvil acepta URLs arbitrarias del usuario, las descarga, las pasa
por un browser headless, las clasifica con un LLM externo y persiste
contenido + metadata en bases de datos multi-tenant. Las amenazas
realistas que tomamos en serio:

| ID | Categoría | Vector | Mitigación principal |
|---|---|---|---|
| T1 | Exposición de servicios | Acceso a Postgres / Redis / Grafana / n8n / RabbitMQ / LiteLLM desde internet | §2 — bind 127.0.0.1 + UFW |
| T2 | SSRF | URL que apunta a un host interno (`localhost`, `cerebro-postgres`, RFC1918, DNS rebinding, redirects) | §4 — `validate_url()` + redirects manuales |
| T3 | Escape de browser headless | 0-day de Chromium explotado por una página maliciosa scrapeada | §5 — `cap_drop=ALL`, `no-new-privileges`, read-only FS, non-root |
| T4 | Brute force / credenciales | Login Grafana/n8n público, SSH password, etc. | §3 + §2 (UIs detrás del firewall) |
| T5 | Clickjacking / MITM downgrade | Frontend embebido en iframe atacante, downgrade HTTP | §6 — `X-Frame-Options`, HSTS |
| T6 | Prompt injection en LLM | Página intenta reescribir el output (`temporal_class=evergreen` falso) | Aceptado — el damage cap es la clasificación, no actions |
| T7 | Container escape vía kernel | LXC comparte kernel con el host hipervisor | Aceptado — mantener host actualizado |

---

## 2. Capa de red — host

### 2.1 Bind de puertos a `127.0.0.1`

**Regla**: todos los `ports:` del `docker-compose.yml` se publican
únicamente en loopback, salvo el sidecar de Tailscale (que no usa
puertos del host).

```yaml
# ❌ Mal — accesible desde internet
ports:
  - "5432:5432"

# ✅ Bien — solo procesos locales del host pueden conectar
ports:
  - "127.0.0.1:5432:5432"
```

Esta regla aplica a TODOS los servicios listados con `ports:`:
`cerebro-api`, `cerebro-web`, `cerebro-traefik`, `cerebro-rabbitmq`,
`cerebro-redis`, `cerebro-postgres`, `cerebro-qdrant`, `cerebro-litellm`,
`cerebro-n8n`, `cerebro-jaeger`, `cerebro-otel`, `cerebro-prometheus`,
`cerebro-grafana`, y los exporters.

El acceso externo público a la app solo entra por el sidecar Tailscale
Funnel (§7), que habla con `cerebro-web` por la red Docker interna
`cerebro-net`, no por puertos del host.

### 2.2 Firewall (UFW)

UFW activo con default `deny incoming`:

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow in on lo
ufw allow from <lan-cidr> to any port 22 proto tcp comment "SSH desde LAN"

# Necesario para que el tráfico Docker inter-container fluya
ufw allow in on docker0
ufw allow in on <bridge-cerebro-net>   # br-XXXXXXXXX (variable)
ufw default allow routed

ufw enable
```

El `<lan-cidr>` se ajusta a la red privada desde la que el operador
administra el host (ej. `10.0.0.0/24` o `<network>/24`). No usar
`0.0.0.0/0` para SSH.

### 2.3 Acceso a UIs administrativas

Grafana, n8n, Jaeger, Prometheus, RabbitMQ management, Traefik
dashboard, Qdrant dashboard y Postgres están **cerrados al mundo**
(solo `127.0.0.1`). Para acceder:

```bash
# Túnel SSH desde tu máquina LAN
ssh -L 3000:localhost:3000 \
    -L 5678:localhost:5678 \
    -L 15672:localhost:15672 \
    -L 16686:localhost:16686 \
    -L 9090:localhost:9090 \
    -L 8080:localhost:8080 \
    <ssh-alias-del-host>

# Abre en tu navegador local:
#   Grafana:           http://localhost:3000
#   n8n:               http://localhost:5678
#   RabbitMQ mgmt:     http://localhost:15672
#   Jaeger:            http://localhost:16686
#   Prometheus:        http://localhost:9090
#   Traefik dashboard: http://localhost:8080
```

---

## 3. SSH

`/etc/ssh/sshd_config.d/99-hardening.conf`:

```
PermitRootLogin prohibit-password
PasswordAuthentication no
ChallengeResponseAuthentication no
KbdInteractiveAuthentication no
PermitEmptyPasswords no
PubkeyAuthentication yes
MaxAuthTries 3
LoginGraceTime 30
ClientAliveInterval 300
ClientAliveCountMax 2
```

**Recargar con `systemctl reload sshd`**, no `restart` — `reload` no
interrumpe sesiones SSH activas. Antes de aplicar:

- Confirma que `~/.ssh/authorized_keys` tiene tu key
- Mantén una segunda sesión SSH abierta como salvaguarda

**No dejar `/root/.ssh/id_*`** (claves privadas) en el host. Si un
atacante compromete el host, no puede saltar a OTRAS máquinas por
SSH. Si necesitas que el host se conecte a otro sistema, usa un
agente forwarded o credenciales con scope mínimo, nunca una key
persistente en disco.

---

## 4. Validación de URLs (anti-SSRF)

### 4.1 Schema Pydantic

```python
# src/ingestion/schemas.py
from pydantic import AnyHttpUrl, field_validator
from ._url_safety import validate_url, UnsafeURLError

class IngestionRequest(BaseModel):
    url: AnyHttpUrl              # restringe scheme a http/https
    tenant_id: str

    @field_validator("url")
    @classmethod
    def _no_internal(cls, v):
        try:
            validate_url(str(v))
        except UnsafeURLError as e:
            raise ValueError(f"URL rechazada: {e}") from e
        return v
```

### 4.2 Helper `validate_url()`

`src/ingestion/_url_safety.py` aplica cinco capas de check:

1. **Allowlist de scheme**: solo `http` y `https`. Rechaza
   `file://`, `javascript:`, `gopher://`, `dict://`, `data:`, etc.
2. **Allowlist negativa de hostnames**: bloquea por nombre todos los
   servicios del compose (`cerebro-postgres`, `cerebro-api`, …),
   `localhost`, y los nombres cortos (`postgres`, `redis`, …).
3. **Sufijos internos**: `.localhost`, `.local`, `.internal`,
   `.cluster.local`, `.docker`, `.compose` rechazados.
4. **IP literal**: si el host es una IP, se verifica `is_private`,
   `is_loopback`, `is_link_local`, `is_multicast`, `is_reserved`,
   `is_unspecified`. Rechaza RFC1918, `127.0.0.0/8`, `169.254.0.0/16`,
   `::1`, multicast, etc.
5. **DNS rebinding**: resuelve el hostname y verifica que **todas**
   las A/AAAA records apunten a IPs públicas. Bloquea ataques donde
   un dominio externo legítimo devuelve `127.0.0.1` o `10.x.x.x`.

### 4.3 Redirects manuales

```python
# src/scraper/strategy.py — BasicHttpStrategy
async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
    current = url
    for hop in range(5):                       # máx 5 hops
        resp = await client.get(current, ...)
        if resp.status_code in (301, 302, 303, 307, 308):
            next_url = urljoin(current, resp.headers["location"])
            validate_url(next_url)             # re-check cada hop
            current = next_url
            continue
        resp.raise_for_status()
        return resp.text
```

Sin esto, una URL externa legítima puede devolver `302 Location:
http://cerebro-postgres:5432` y bypass-ar la validación inicial.

### 4.4 Defense in depth

`validate_url()` se invoca **dos veces** en el pipeline:

- En el endpoint `/ingest` (entrada).
- En el worker scraper, justo antes de hacer el fetch (por si la
  URL llegó a la cola por otra ruta).

---

## 5. Hardening de containers

### 5.1 Usuarios non-root

Todos los workers propios corren con UID 1000 (`cerebro`):

```dockerfile
RUN groupadd -r cerebro && useradd -r -g cerebro -u 1000 cerebro
USER cerebro
```

El frontend Next.js corre con el user `node` (UID 1000 en la imagen
base). LiteLLM y Postgres corren con sus propios UIDs no-root salvo
LiteLLM que usa `root` por requisito de la imagen oficial; queda
mitigado por las capas siguientes.

### 5.2 `cap_drop` + `no-new-privileges`

Aplicado en `docker-compose.yml` a los 7 servicios de aplicación:

```yaml
ingestion-api: &harden
  cap_drop: [ALL]
  security_opt:
    - "no-new-privileges:true"

cerebro-api: *harden
cerebro-web: *harden
scraper-worker: *harden
embedder-worker: *harden
outbox-worker: *harden
notifier-worker: *harden
```

`cap_drop: [ALL]` elimina TODAS las capabilities de Linux
(`NET_RAW`, `SETUID`, `SYS_ADMIN`, …). El proceso queda restringido a
operaciones de usuario sin privilegios, aunque corra como root dentro
del container.

`no-new-privileges:true` impide que un proceso obtenga capabilities
adicionales vía `execve()` — los binarios SUID dejan de poder
escalar.

### 5.3 Read-only filesystem (scraper)

El servicio con mayor superficie de ataque es el scraper (ejecuta
Chromium con páginas web arbitrarias). Se le aplica el blindaje extra:

```yaml
scraper-worker:
  cap_drop: [ALL]
  security_opt: ["no-new-privileges:true"]
  read_only: true                    # root FS de solo lectura
  tmpfs:
    - /tmp:exec,mode=1777,size=512m  # Chromium necesita /tmp con exec
    - /run:size=64m
```

Los volúmenes existentes (`/data`, `/home/cerebro/.cache` para el
profile de Playwright) siguen escribibles porque son mounts
independientes del rootfs.

**Justificación**: el scraper invoca Chromium con `--no-sandbox` (los
LXC sin user-namespaces no soportan el sandbox de Chrome). Si una
página explota un 0-day de Chromium:

- ❌ No puede usar capabilities (NET_RAW, MKNOD, SETUID, SYS_ADMIN, …)
- ❌ No puede escalar vía binarios SUID
- ❌ No puede persistir nada en el rootfs (solo `/tmp` tmpfs efímero
  que se borra al reiniciar)
- ❌ No puede tocar otros containers en `cerebro-net` que escuchen en
  protocolos no-HTTP — Postgres, Redis, RabbitMQ usan protocolos
  binarios incompatibles con `fetch()` desde JS
- ✅ Sí puede consumir tokens del LLM gateway (LiteLLM) — el damage
  cap aquí es coste, no exfiltración

### 5.4 Docker socket read-only en Traefik

Traefik necesita leer labels de containers para hacer routing. Su
mount del docker socket es **solo lectura**:

```yaml
cerebro-traefik:
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock:ro
```

Sin `:ro`, una vulnerabilidad en Traefik permitiría root del host vía
`docker run --privileged`. Con `:ro`, queda limitado a `inspect` /
`list` (lectura).

### 5.5 Verificación

```bash
docker inspect <container> --format \
  'caps={{.HostConfig.CapDrop}} no-new-priv={{.HostConfig.SecurityOpt}} ro={{.HostConfig.ReadonlyRootfs}}'
```

Debería devolver `caps=[ALL]`, `no-new-priv=[no-new-privileges:true]`,
y para el scraper `ro=true`.

---

## 6. Security headers del frontend

`src/frontend/next.config.ts` añade `async headers()` que se aplica a
toda response del frontend:

```typescript
async headers() {
  return [{
    source: "/(.*)",
    headers: [
      { key: "Strict-Transport-Security",
        value: "max-age=63072000; includeSubDomains" },
      { key: "X-Frame-Options",         value: "DENY" },
      { key: "X-Content-Type-Options",  value: "nosniff" },
      { key: "Referrer-Policy",         value: "strict-origin-when-cross-origin" },
      { key: "Permissions-Policy",      value:
          "camera=(), microphone=(), geolocation=(), payment=(), usb=(), bluetooth=()" },
    ],
  }];
}
```

**Importante** sobre Tailscale Funnel: el TLS termina en el sidecar
Tailscale y el proxy a `cerebro-web` es plain HTTP por la red Docker.
Los headers viajan en el body HTTP de vuelta al cliente, y la conexión
edge↔cliente sí es HTTPS — el browser los ve y los aplica.

### 6.1 `metadataBase`

Sin `metadataBase`, Next.js absolutiza las URLs de `og:image`,
`twitter:image`, etc. usando `http://localhost:3000` como base. El
HTML resultante incluye refs a HTTP cuando se sirve por HTTPS, y los
browsers lo marcan como mixed content.

```typescript
// src/frontend/app/layout.tsx
export const metadata: Metadata = {
  metadataBase: new URL(
    process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3001"
  ),
  // …
};
```

`NEXT_PUBLIC_*` se interpola en build time, así que hay que pasarlo
como `--build-arg`:

```yaml
# docker-compose.yml
cerebro-web:
  build:
    context: .
    dockerfile: infra/frontend.Dockerfile
    args:
      NEXT_PUBLIC_SITE_URL: ${NEXT_PUBLIC_SITE_URL:-}
```

```dockerfile
# infra/frontend.Dockerfile
ARG NEXT_PUBLIC_SITE_URL=
ENV NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL
RUN npm run build
```

En despliegues privados (`.env` sin `NEXT_PUBLIC_SITE_URL`), el
fallback `http://localhost:3001` no causa mixed content porque el
acceso interno va por HTTP plano.

---

## 7. Acceso público vía Tailscale Funnel

El sidecar `tailscale-web` (profile `public`) es la **única ruta**
para tráfico externo entrante. No hay puertos públicos en el host.

### 7.1 Flujo

```
Internet
    │  HTTPS / TLS 1.3
    ▼
Tailscale edge (DERP relay)
    │  WireGuard UDP (saliente del sidecar)
    ▼
cerebro-tailscale-web (sidecar)
    │  HTTP plano por red Docker cerebro-net
    ▼
cerebro-web (Next.js)
    │  rewrites server-side
    ▼
cerebro-api (FastAPI)
```

El browser jamás habla con `cerebro-api` directamente; todo va por
Next.js rewrites (`/api/*` → `http://cerebro-api:8001` por red Docker
interna). El usuario externo solo conoce el dominio Funnel.

### 7.2 Configuración mínima del tailnet

Antes de levantar el sidecar:

1. **Activar HTTPS Certificates** en
   `https://login.tailscale.com/admin/dns`. Necesario para que
   Tailscale emita el cert Let's Encrypt automáticamente.
2. **Activar Funnel para el tag** en la ACL (`File` editor):

   ```json
   {
     "tagOwners": {
       "tag:funnel-web": ["autogroup:admin"]
     },
     "nodeAttrs": [
       {
         "target": ["tag:funnel-web"],
         "attr":   ["funnel"]
       }
     ],
     "grants": [
       { "src": ["*"], "dst": ["*"], "ip": ["*"] }
     ]
   }
   ```

   Sin el bloque `nodeAttrs`, el sidecar pide Funnel pero el control
   plane lo rechaza y el DNS público nunca se publica.
3. **Crear authkey** en `https://login.tailscale.com/admin/settings/keys`
   con: Reusable ON, Ephemeral OFF, Tag `tag:funnel-web`.

### 7.3 `serve-web.json`

`infra/tailscale/serve-web.json`:

```json
{
  "TCP": { "443": { "HTTPS": true } },
  "Web": {
    "${TS_CERT_DOMAIN}:443": {
      "Handlers": {
        "/": { "Proxy": "http://cerebro-web:3001" }
      }
    }
  },
  "AllowFunnel": {
    "${TS_CERT_DOMAIN}:443": true
  }
}
```

Apunta al puerto **3001** (Next.js), no al 3000 (que es Grafana).

### 7.4 Hardening adicional del nodo público (opcional)

ACL para aislar el sidecar dentro de la tailnet:

```json
{
  "grants": [
    { "src": ["autogroup:admin"],    "dst": ["*"],               "ip": ["*"] },
    { "src": ["*"],                  "dst": ["tag:funnel-web"],  "ip": ["443"] }
  ]
}
```

Con esto, si una vulnerabilidad de Tailscale o de Traefik fuera
explotable, el atacante quedaría aislado: el nodo público solo puede
recibir en su :443, no puede iniciar conexiones a otros nodos de la
tailnet.

---

## 8. Lo que no mitigamos

| Vector | Razón | Mitigación si se vuelve crítico |
|---|---|---|
| **Prompt injection en LLM** | El contenido scrapeado va al prompt. Damage cap: solo afecta a la clasificación temporal del recurso, no a actions del sistema | Separar prompt + content con delimitadores fuertes; tagging de output con "from user" |
| **Network segmentation interna del scraper** | El scraper necesita Postgres + Redis + LiteLLM + RabbitMQ; la mayoría de servicios internos. No es viable segmentar sin refactor mayor | Splitting en dos containers (worker python + browser headless aislado) |
| **Container escape vía kernel** | LXC comparte kernel con el host hipervisor | Mantener Proxmox/host actualizado; considerar VM en lugar de LXC para servicios públicos |
| **Phishing del usuario por dominio Funnel feo** | URLs `*.ts.net` no inspiran confianza | Cloudflare en frente con dominio propio, o plan Tailscale Business con custom domain |

---

## 9. Checklist pre-deploy

Antes de exponer una nueva instancia a internet, verifica en orden:

### Host

- [ ] UFW activo: `ufw status verbose`
- [ ] Default `deny incoming`: revisar línea `Default:`
- [ ] Regla SSH solo desde `<lan-cidr>` o equivalente
- [ ] No hay `~/.ssh/id_*` en el host (no SSH keys privadas)
- [ ] `sshd_config`: `PermitRootLogin prohibit-password`,
      `PasswordAuthentication no`
- [ ] Servicios no-LinkAnvil parados (tinyproxy, open-resolvers, etc.):
      `ss -tlnp` y `systemctl list-units --type=service --state=running`

### Docker / compose

- [ ] Todos los `ports:` están en `127.0.0.1:`
- [ ] Servicios de aplicación tienen `cap_drop: [ALL]` +
      `security_opt: [no-new-privileges:true]`
- [ ] Scraper tiene `read_only: true` + `tmpfs`
- [ ] Traefik monta `docker.sock` con `:ro`
- [ ] Ningún container con `privileged: true`
- [ ] Ningún container con `network_mode: host`

### Aplicación

- [ ] `.env` no commiteado al repositorio
- [ ] `.env` tiene secretos generados aleatoriamente (no
      `_CHANGE_ME` placeholders)
- [ ] `LLM_KEYS_ENCRYPTION_KEY` único por instancia (Fernet)
- [ ] `JWT_SECRET` único por instancia
- [ ] `AUDIT_CRON_TOKEN` único por instancia
- [ ] `validate_url()` accesible desde tests:
      `python -c "from _url_safety import validate_url; validate_url('http://localhost/x')"`
      debe lanzar `UnsafeURLError`

### Tailscale (si modo público)

- [ ] HTTPS Certificates activado en admin
- [ ] ACL con `tagOwners` para el tag del Funnel
- [ ] ACL con `nodeAttrs.attr=["funnel"]` para el tag
- [ ] `authkey`: Reusable ON, Ephemeral OFF, Tag asignado
- [ ] `serve-web.json` apunta a `cerebro-web:3001`
- [ ] `NEXT_PUBLIC_SITE_URL` setteado en `.env` con la URL Funnel
      ANTES del primer build de `cerebro-web`

### Frontend

- [ ] HTML servido NO contiene `http://localhost`:
      `curl -s https://<funnel-url>/ | grep -c 'http://localhost'` → `0`
- [ ] Security headers presentes:
      `curl -sI https://<funnel-url>/` → verificar `strict-transport-security`,
      `x-frame-options`, `x-content-type-options`, `referrer-policy`,
      `permissions-policy`

---

## 10. Comandos de verificación post-deploy

```bash
# 1) Puertos públicos del host — solo SSH desde fuera de la LAN
nmap -Pn -p 22,80,443,3000,5432,5678,8001,8080 <host-public-ip>
# Resultado esperado: solo 22 visible (y filtered si tu IP no está en
# la allowlist UFW). Todos los demás "filtered" o "host down".

# 2) Funnel público responde
curl -m 10 -I https://<funnel-url>/
# Resultado: HTTP/2 200 + headers de seguridad

# 3) Anti-SSRF — pedir un recurso interno por la API expuesta
curl -X POST https://<funnel-url>/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"url":"http://localhost:5432","tenant_id":"x"}'
# Resultado: 422 con el detalle del validator

# 4) Anti-SSRF — schema bloqueado
curl -X POST https://<funnel-url>/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"url":"file:///etc/passwd","tenant_id":"x"}'
# Resultado: 422

# 5) Containers hardened
docker ps --format '{{.Names}}' | xargs -I{} sh -c '
  docker inspect {} --format "{{.Name}} caps={{.HostConfig.CapDrop}} \
    no-priv={{.HostConfig.SecurityOpt}} ro={{.HostConfig.ReadonlyRootfs}}"
' | grep -E 'cerebro-(api|web|scraper|embedder|notifier|outbox|ingestion)'
# Resultado: cap_drop=[ALL] + no-new-privileges en todos; ro=true en scraper

# 6) UFW activo
ufw status verbose | head -10
# Resultado: Status: active, Default: deny (incoming)

# 7) SSH endurecido
sshd -T 2>&1 | grep -iE '^(permitroot|passwordauth|maxauth)'
# Resultado: permitrootlogin without-password, passwordauthentication no,
#            maxauthtries 3
```

---

## 11. Cambios de seguridad por release

Las modificaciones de este documento se trazan en `git log` con el
prefijo `sec(...)`:

```bash
git log --oneline --grep '^sec' | head
```

Toda nueva capa de seguridad introducida debe:

1. Tener un commit `sec(scope): ...` con explicación de qué amenaza
   mitiga.
2. Añadir una entrada en este documento bajo la sección
   correspondiente.
3. Añadir el comando de verificación al §10.
4. Si introduce un nuevo nombre técnico, añadir entrada al
   [Glosario](./10-Glosario).
