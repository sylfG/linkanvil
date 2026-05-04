# Workflows n8n

Workflows reproducibles del proyecto linkanvil. Se versiona el JSON
exportado de n8n para que un `docker compose up` limpio pueda
reconstruir los crons sin clicks manuales.

## Importar tras `docker compose up`

1. Asegurarse de que la env `AUDIT_CRON_TOKEN` esté en `.env` y que la
   API esté arriba con el mismo token (`docker compose config` para
   verificar).
2. Abrir n8n: `http://n8n.localhost` (o `:5678` según overlay).
3. Workflow → Import from File → seleccionar el JSON correspondiente.
4. Activar el workflow (toggle Active).
5. (Opcional) Ejecutar manualmente para probar — debe responder 200 y
   loguear `{cuarentenados, expirados}`.

Alternativa programática: usar `bootstrap-apikey.py` para obtener una
API key y `POST /api/v1/workflows` con el JSON.

## Workflows disponibles

| Archivo | Trigger | Acción |
| --- | --- | --- |
| `audit_cron_daily.json` | Cron `0 3 * * *` | `POST /admin/audit-cron` con `X-Admin-Token`. Mueve recursos vencidos a cuarentena y expira los que agotaron período de gracia. |
