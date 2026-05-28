-- 0011_staged_embeddings_cache.sql
--
-- Slice 6.5 — Cache de embeddings de los recursos staged del demo.
--
-- Cada `POST /auth/demo-start` crea un sub-tenant nuevo con 3 recursos
-- sintéticos (definidos en `src/api/database.py::_STAGED_RECURSOS`). Para
-- que el RAG encuentre estos recursos, Slice 6.4 los embebía vía LiteLLM
-- en cada session-start. Eso gasta tokens innecesariamente: el contenido
-- de los 3 staged es idéntico para todas las sesiones, solo cambia el
-- tenant_id.
--
-- Esta tabla cachea los vectores pre-computados. Se rellena UNA VEZ con
-- `ops/build_staged_embeddings.py` (idempotente vía ON CONFLICT). El
-- endpoint demo-start lee el vector desde aquí en vez de pegarle a
-- LiteLLM. Hits típicos: < 5ms vs ~300-500ms del round-trip al proxy.
--
-- Aislación per-tenant: el cache es READ-ONLY desde la perspectiva del
-- session-start. Los recursos efímeros que se generan en cada sesión
-- (`recursos`, `usuario_recursos`, Qdrant points) viven en el sub-tenant
-- y siguen siendo borrados por el cleanup cascade habitual. Esta tabla
-- nunca se toca durante la vida de una sesión.

BEGIN;

CREATE TABLE IF NOT EXISTS cerebro.staged_embeddings_cache (
    idx         INT PRIMARY KEY,           -- coincide con el índice 0/1/2 de _STAGED_RECURSOS
    titulo      TEXT NOT NULL,
    resumen     TEXT NOT NULL,
    categoria   TEXT NOT NULL,
    chunk_text  TEXT NOT NULL,             -- texto que se embebió (titulo + resumen)
    embedding   FLOAT8[] NOT NULL,          -- vector pre-computado por LiteLLM
    model       TEXT NOT NULL DEFAULT 'cerebro-embeddings',
    dims        INT NOT NULL,              -- length(embedding); útil para detectar drift
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE cerebro.staged_embeddings_cache IS
    'Cache de embeddings precomputados de los 3 recursos staged del demo. '
    'Se rellena con ops/build_staged_embeddings.py. Permite que cada '
    '/auth/demo-start indexe los recursos en Qdrant SIN llamar a LiteLLM.';

COMMENT ON COLUMN cerebro.staged_embeddings_cache.idx IS
    'Coincide con la posición en _STAGED_RECURSOS (0=Conferencia DevOps, '
    '1=Webinar RAG, 2=Hackathon LinkAnvil). Sirve para emparejar el '
    'recurso recién insertado en la sesión demo con su vector cacheado.';

COMMENT ON COLUMN cerebro.staged_embeddings_cache.dims IS
    'Dimensiones del vector. Si el script de rebuild detecta un dims '
    'distinto al cacheado, indica que el modelo de embeddings cambió en '
    'LiteLLM y conviene regenerar TODOS los chunks (no solo los staged).';

COMMIT;
