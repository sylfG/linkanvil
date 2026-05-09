# Workflows n8n

Workflows reproducibles del proyecto linkanvil. Se versiona el JSON
exportado de n8n para que un `docker compose up` limpio pueda
reconstruir los crons sin clicks manuales.

## ⚙️ Setup inicial de n8n

Tras `docker compose up`, espera a que n8n esté listo (~2 minutos). Luego:

### 1️⃣ Crear API key en n8n

1. Accede a: `http://localhost:5678` 
   - User: `admin`
   - Password: valor de `N8N_PASSWORD` en `.env`
2. Navega a: **Settings** → **API Tokens**
3. Click **"Create API Token"**
4. Copia el token generado (verás algo como `n8n_api_...`)

### 2️⃣ Guardar API key en `.env`

Edita tu `.env` y reemplaza el valor de `N8N_API_KEY`:

```bash
N8N_API_KEY=<token_que_copiaste>
```

### 3️⃣ Ejecutar bootstrap automático

El bootstrap importará y activará todos los workflows automáticamente:

```bash
docker compose restart n8n-bootstrap
docker logs -f cerebro-n8n-bootstrap
```

Verás algo como:
```
Importando 1 workflow(s)…
  ✓ Workflow 'linkanvil — audit cron diario' importado (id: 123)
    → Workflow activado
✓ Bootstrap completado
```

## 🤖 Agregar nuevos workflows

1. En n8n UI: **Workflow → Export as JSON**
2. Guardar en: `infra/n8n/workflows/<nombre>.json`
3. Editar JSON: asegurar que `"active": true` si deseas auto-activar
4. Re-ejecutar bootstrap:
   ```bash
   docker compose restart n8n-bootstrap
   ```

## 🧪 Probar workflow manualmente

Tras activarlo, puedes ejecutarlo manualmente desde la UI:

1. Abrir workflow en n8n
2. Click **"Execute Workflow"**
3. Debe responder con status 200 y loguear en la API

Alternativa programática: usar `bootstrap-apikey.py` para obtener una
API key y `POST /api/v1/workflows` con el JSON.

## Workflows disponibles

| Archivo | Trigger | Acción |
| --- | --- | --- |
| `audit_cron_daily.json` | Cron `0 3 * * *` | `POST /admin/audit-cron` con `X-Admin-Token`. Mueve recursos vencidos a cuarentena y expira los que agotaron período de gracia. |
