# Architecture Rules — linkanvil

## Invariantes de arquitectura

### Multi-tenancy
- Toda query a `cerebro.*` DEBE filtrar por `tenant_id` — excepto `recursos` (tabla global de URLs deduplicadas)
- Los chunks en Qdrant (`cerebro_chunks`) SIEMPRE llevan `tenant_id` en el payload
- NUNCA mezclar datos de tenants distintos en una respuesta de API

### Outbox pattern
- Las notificaciones externas NUNCA se envían directamente desde workers
- Toda notificación pasa por `cerebro.outbox_eventos` → `outbox-worker`
- Si falla el INSERT en `outbox_eventos`, la transacción entera debe hacer rollback

### Embedding pipeline
- El límite del modelo de embedding es 512 tokens ≈ 1400 chars para texto en inglés, 1300 chars en español
- `_chunk_text()` debe mantener `target_chars ≤ 1200` — NO aumentar sin cambiar el modelo
- La similitud coseno SIEMPRE se clampea: `min(value, 1.0)` antes de insertar en `grafo_relaciones`

### Separación de responsabilidades
- `scraper-worker`: extrae texto (no embed, no chunk)
- `embedder-worker`: embed doc-level + chunk RAG + semantic graph (no HTTP externo salvo LiteLLM)
- `ingestion-api`: recibe requests HTTP, publica a RabbitMQ (no procesa contenido)
- `cerebro-api`: sirve queries RAG y gestión de recursos (no scraping directo)

### Consistencia de datos
- Si `contenido IS NULL` en `recursos`, el recurso es una URL con paywall — comportamiento esperado
- `grafo_relaciones.similitud` tiene CHECK `BETWEEN 0 AND 1` — respetar siempre
- Los UUIDs de recursos son globales — no son per-tenant
