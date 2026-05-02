<div align="center">
  <img src="../public/logo-light.png" alt="Logo" width="80" height="80" class="light-only">
  <img src="../public/logo-dark.png" alt="Logo" width="80" height="80" class="dark-only">


# 🖼️ Documentación Visual y Diagramas C4 — LinkAnvil

</div>


Este documento provee la notación visual técnica bajo el estándar C4 Model, detallando la interacción de contenedores y el flujo distribuido de la arquitectura event-driven.

---

## Nivel 1: Diagrama de Contexto

> Muestra cómo LinkAnvil encaja en el ecosistema, las interacciones con el usuario humano y los sistemas externos.

```mermaid
C4Context
    title Diagrama de Contexto del Sistema - LinkAnvil

    Person(usuario, "Usuario (Dueño)", "Interactúa para capturar enlaces, conversar con su base de conocimiento y revisar métricas.")

    System(cerebro, "LinkAnvil", "Filtra, ingesta, vectoriza y provee respuestas RAG sobre conocimiento estructurado localmente.")

    System_Ext(telegram, "Telegram API", "Canal omnicanal secundario para enviar URLs y reanudar sesiones del chatbot.")
    System_Ext(fuentes, "Fuentes de Datos Web", "Páginas web, APIs y SPAs de donde el sistema extrae el contenido.")
    System_Ext(llms, "Modelos de Lenguaje (LLMs)", "APIs externas (OpenAI, Anthropic, locales) usadas como motor de razonamiento.")

    Rel(usuario, cerebro, "Captura información y consulta el panel/chat", "HTTPS/WSS")
    Rel(usuario, telegram, "Envía mensajes a su bot personal")
    Rel(telegram, cerebro, "Redirige peticiones webhooks", "HTTPS")
    Rel(cerebro, fuentes, "Extrae contenido de URLs asincrónicamente", "HTTPS/Scrapling")
    Rel(cerebro, llms, "Delega resúmenes, estructuración y embeddings", "HTTPS/REST")
```

---

## Nivel 2: Diagrama de Contenedores

> Detalla las piezas principales del software dentro de la red aislada `cerebro-net` y sus responsabilidades.

```mermaid
C4Container
    title Arquitectura Interna — 21 contenedores en cerebro-net

    Person(usuario, "Usuario")
    System_Ext(telegram, "Telegram Bot")
    System_Ext(llms, "LLM Providers")

    Container_Boundary(cerebro_net, "Red Virtual Segura (cerebro-net)") {

        Container(traefik, "API Gateway", "Traefik v3.6", "Único punto de entrada. Rate limiting, enrutamiento dinámico, Trace-ID OTel, TLS en producción.")

        Container(ingestion, "Ingestion API", "FastAPI · redis.asyncio", "Recibe URLs, Bloom Filter deduplicación, rate limiter INCR atómico, publica a RabbitMQ.")
        Container(api, "cerebro-api", "FastAPI · asyncpg", "Auth JWT httpOnly cookie + CSRF, chat RAG SSE, CRUD sesiones/mensajes, paginación.")
        Container(web, "cerebro-web", "Next.js 15 · Zustand", "UI chat, historial, panel de recursos. Store API-backed (sin localStorage).")

        Container(scraper, "cerebro-scraper", "Python · Playwright", "Consume q.url.ingesta. Scrapling/Chromium headless. Heartbeat Redis.")
        Container(embedder, "cerebro-embedder", "Python · httpx pool", "Consume q.embeddings. Genera vectores vía LiteLLM, inserta en Qdrant. Heartbeat Redis.")
        Container(outbox, "cerebro-outbox", "Python", "Polling outbox_eventos Postgres → publica en RabbitMQ. Garantiza consistencia eventual.")

        Container(litellm, "LiteLLM Gateway", "LiteLLM", "Proxy multi-proveedor. Circuit Breaker, Fallback, caché Redis de prompts.")
        Container(n8n, "n8n Orquestador", "n8n", "Workflows visuales: scraping ligero, Telegram, curación nocturna.")

        ContainerDb(postgres, "PostgreSQL", "postgres:16-alpine", "Schema cerebro (aislado de Prisma LiteLLM): recursos, sesiones_chat, mensajes_chat, outbox_eventos, usuarios, relaciones.")
        ContainerDb(redis, "Redis Stack", "redis-stack-server", "Bloom Filter, rate limiting, heartbeat workers, caché LiteLLM.")
        ContainerDb(rabbitmq, "RabbitMQ", "rabbitmq:3.13", "Colas: q.url.ingesta, q.embeddings. DLQ: q.embeddings.fallidos.")
        ContainerDb(qdrant, "Qdrant", "qdrant:v1.17.1", "Almacena y busca embeddings por similitud coseno, filtrado por tenant_id.")
    }

    Rel(usuario, traefik, "HTTPS", "80/443")
    Rel(telegram, traefik, "Webhooks", "HTTPS")

    Rel(traefik, ingestion, "ingest.*")
    Rel(traefik, api, "api.*")
    Rel(traefik, web, "cerebro.*")
    Rel(traefik, n8n, "n8n.*")

    Rel(web, api, "proxy server-side", "HTTP")
    Rel(api, postgres, "auth, sesiones, mensajes", "asyncpg")
    Rel(api, redis, "rate limiting, caché", "redis.asyncio")
    Rel(api, litellm, "embeddings + chat stream", "httpx")
    Rel(api, qdrant, "búsqueda vectorial RAG", "httpx")

    Rel(ingestion, redis, "Bloom Filter + rate limit", "redis.asyncio")
    Rel(ingestion, rabbitmq, "publica q.url.ingesta", "AMQP")

    Rel(scraper, rabbitmq, "consume q.url.ingesta", "AMQP")
    Rel(scraper, litellm, "analiza texto", "httpx")
    Rel(scraper, postgres, "INSERT recursos + outbox", "asyncpg")
    Rel(scraper, redis, "heartbeat TTL", "redis")

    Rel(outbox, postgres, "lee outbox_eventos", "asyncpg")
    Rel(outbox, rabbitmq, "publica q.embeddings", "AMQP")

    Rel(embedder, rabbitmq, "consume q.embeddings", "AMQP")
    Rel(embedder, litellm, "genera embedding", "httpx")
    Rel(embedder, qdrant, "upsert vector + tenant_id", "httpx")

    Rel(litellm, llms, "Fallback autorizado", "HTTPS")
    Rel(litellm, redis, "caché de prompts", "redis")
```

---

## Diagrama de Flujo: Ingesta Asíncrona

> Flujo completo desde que el usuario envía una URL hasta que queda vectorizada en Qdrant.

```mermaid
sequenceDiagram
    autonumber
    actor U as Usuario/Bot
    participant IG as cerebro-ingestion
    participant RD as Redis (Bloom Filter)
    participant MQ as RabbitMQ
    participant SC as cerebro-scraper
    participant LLM as LiteLLM
    participant PG as PostgreSQL (schema cerebro)
    participant OB as cerebro-outbox
    participant EM as cerebro-embedder
    participant QD as Qdrant

    U->>IG: POST /ingest {url, tenant_id}
    IG->>RD: BF.EXISTS url_hash (< 1ms)

    alt URL duplicada
        RD-->>IG: true
        IG-->>U: 409 Conflict
    else URL nueva
        RD-->>IG: false
        IG->>RD: INCR rate_limit:{ip} (atómico)
        IG->>RD: BF.ADD url_hash
        IG->>MQ: publish q.url.ingesta
        IG-->>U: 202 Accepted

        Note over MQ, SC: Procesamiento asíncrono
        SC->>MQ: consume mensaje
        SC->>SC: Scraping (static/Playwright según origen)
        SC->>LLM: POST /chat (extrae JSON: titulo, resumen, tags, volatilidad)
        LLM-->>SC: JSON estructurado (Pydantic validado)
        SC->>PG: BEGIN TRANSACTION
        SC->>PG: INSERT cerebro.recursos (estado='procesando')
        SC->>PG: INSERT cerebro.outbox_eventos (evento='embedding.requerido')
        SC->>PG: COMMIT

        Note over OB, MQ: Outbox Publisher (polling)
        OB->>PG: SELECT outbox_eventos WHERE estado='pendiente'
        PG-->>OB: evento embedding.requerido
        OB->>MQ: publish q.embeddings
        OB->>PG: UPDATE outbox_eventos SET estado='procesado'

        Note over EM, QD: Embedder Worker
        EM->>MQ: consume q.embeddings
        EM->>LLM: POST /v1/embeddings (texto del recurso)
        LLM-->>EM: vector [0.12, -0.45, ...]
        EM->>QD: upsert {id, vector, payload: {tenant_id}}
        EM->>PG: UPDATE recursos SET estado='activo', embedding_version=1
    end
```

---

## Diagrama de Flujo: Chat RAG con SSE Streaming

> Cómo el usuario obtiene respuestas fundamentadas en su base de conocimiento personal.

```mermaid
sequenceDiagram
    autonumber
    actor U as Usuario
    participant WB as cerebro-web (Next.js)
    participant AP as cerebro-api (FastAPI)
    participant RD as Redis
    participant LLM as LiteLLM
    participant QD as Qdrant
    participant PG as PostgreSQL

    U->>WB: escribe pregunta y envía
    WB->>AP: POST /chat {messages, session_id}\ncookies: SESSION_COOKIE + CSRF_COOKIE\nheader: X-CSRF-Token
    AP->>AP: verifica JWT (SESSION_COOKIE httpOnly)
    AP->>AP: verifica CSRF (header == cookie)
    AP->>RD: INCR chat_rate:{tenant_id} (30/min)

    AP->>LLM: genera embedding de la pregunta
    LLM-->>AP: vector semántico

    AP->>QD: búsqueda coseno\nfilter: {tenant_id: "..."}\ntop_k: 5, score_threshold: 0.85
    QD-->>AP: documentos relevantes con scores

    AP->>LLM: stream(\n  system: "Eres un asistente...",\n  context: [documentos RAG],\n  messages: [...historial]\n)

    loop SSE chunks
        LLM-->>AP: chunk de texto
        AP-->>WB: event: chunk, data: {text}
    end

    AP-->>WB: event: sources, data: {fuentes RAG}
    AP-->>WB: event: done

    AP->>PG: INSERT cerebro.mensajes_chat\n(user_message + assistant_message\ncon fuentes JSONB)
    WB-->>U: muestra respuesta completa + fuentes
```

---

## Diagrama de Flujo: Autenticación con Cookie httpOnly

> El modelo de seguridad completo para el navegador: por qué no se usa localStorage.

```mermaid
sequenceDiagram
    autonumber
    actor U as Usuario
    participant WB as cerebro-web
    participant AP as cerebro-api
    participant RD as Redis (rate limit)
    participant PG as PostgreSQL (schema cerebro)

    U->>WB: POST /auth/login {email, password}
    WB->>AP: POST /auth/login\n(credentials: "include")
    AP->>RD: INCR login_rate:{ip}\n(límite: 5/min)

    alt Rate limit superado
        AP-->>WB: 429 Too Many Requests
    else Dentro del límite
        AP->>PG: SELECT * FROM cerebro.usuarios\nWHERE email = ?
        PG-->>AP: usuario + password_hash

        alt Contraseña incorrecta
            AP-->>WB: 401 Unauthorized
        else Login correcto
            AP->>AP: genera JWT (exp: 8h)
            AP->>AP: genera CSRF token (urandom 32 bytes)
            AP-->>WB: 200 OK\nSet-Cookie: SESSION_COOKIE=<JWT>\n  httpOnly, samesite=lax, secure (prod)\nSet-Cookie: CSRF_COOKIE=<csrf_token>\n  samesite=lax (legible por JS)
        end
    end

    Note over WB: JS lee document.cookie para CSRF_COOKIE\ny lo almacena en memoria (no en localStorage)

    U->>WB: acción que modifica estado (ej: POST /chat)
    WB->>AP: POST /chat\ncookies: SESSION_COOKIE (httpOnly, auto)\nheader: X-CSRF-Token: <csrf_token>
    AP->>AP: extrae JWT de SESSION_COOKIE
    AP->>AP: verifica X-CSRF-Token == valor en CSRF_COOKIE
    AP-->>WB: respuesta autorizada
```

---

## Diagrama de Flujo: Pipeline de Observabilidad

> Cómo fluye la telemetría desde los servicios hasta Grafana.

```mermaid
graph LR
    classDef service fill:#1f3a2a,stroke:#10b981,color:#fff
    classDef collector fill:#1e3a8a,stroke:#8b5cf6,color:#fff
    classDef storage fill:#374151,stroke:#f59e0b,color:#fff
    classDef viz fill:#2b3c5a,stroke:#3b82f6,color:#fff

    Traefik["Traefik\n(OTLP HTTP traces)"]:::service
    API["cerebro-api\n(OTLP HTTP traces)"]:::service
    PG_exp["postgres-exporter\n(métricas SQL)"]:::service
    RMQ_exp["rabbitmq-exporter\n(métricas AMQP)"]:::service
    RD_exp["redis-exporter\n(métricas Redis)"]:::service

    OTel["OTel Collector\n(4317/4318)"]:::collector

    Jaeger["Jaeger\n(trazas distribuidas)"]:::storage
    Prometheus["Prometheus\n(series temporales\n+ alertas)"]:::storage

    Grafana["Grafana\n(dashboards unificados)"]:::viz

    Traefik -->|trazas OTLP| OTel
    API -->|trazas OTLP| OTel
    OTel -->|exporta trazas| Jaeger
    OTel -->|expone métricas| Prometheus

    PG_exp -->|scrape| Prometheus
    RMQ_exp -->|scrape| Prometheus
    RD_exp -->|scrape| Prometheus

    Grafana -->|query| Prometheus
    Grafana -->|query| Jaeger
```
