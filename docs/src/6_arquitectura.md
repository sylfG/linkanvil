# 🏗️ Arquitectura e Infraestructura Local — Segundo Cerebro Autónomo

Este documento detalla la infraestructura local basada en Docker Compose del proyecto **Segundo Cerebro Autónomo**, explicando la topología de la red, los componentes desplegados, sus responsabilidades y cómo fluye la información a través del sistema.

---

## 1. Topología del Sistema y Conexiones

Todos los servicios se ejecutan dentro del mismo entorno aislado interconectado mediante la red Docker privada `cerebro-net`. Las peticiones externas entran exclusivamente a través de **Traefik**, garantizando control de tráfico, balanceo y autenticación perimetral.

```mermaid
graph TD
    %% Estilos
    classDef proxy fill:#2b3c5a,stroke:#3b82f6,stroke-width:2px,color:#fff
    classDef engine fill:#1f2937,stroke:#10b981,stroke-width:2px,color:#fff
    classDef storage fill:#374151,stroke:#f59e0b,stroke-width:2px,color:#fff
    classDef observability fill:#1e3a8a,stroke:#8b5cf6,stroke-width:2px,color:#fff

    User((Usuario/API))

    subgraph Red Interna ["Red Docker (cerebro-net)"]
        Traefik["🔀 Traefik (API Gateway)"]:::proxy
        
        subgraph Motor de Procesamiento
            n8n["🔄 n8n (Orquestador)"]:::engine
            LiteLLM["🤖 LiteLLM Gateway"]:::engine
        end
        
        subgraph Capa de Almacenamiento y Eventos
            RabbitMQ["📨 RabbitMQ (Mensajería)"]:::storage
            Redis["⚡ Redis (Caché & Sesiones)"]:::storage
            Postgres["🗄️ PostgreSQL (Outbox+Relacional)"]:::storage
            Qdrant["🧠 Qdrant (Base Vectorial)"]:::storage
        end
        
        subgraph Observabilidad
            OTel["📡 OTel Collector"]:::observability
            Jaeger["🔭 Jaeger (Trazas)"]:::observability
            Prometheus["📊 Prometheus (Métricas)"]:::observability
            Grafana["📈 Grafana (Dashboards)"]:::observability
        end
    end

    %% Conexiones de Entrada
    User -->|":80 / :443"| Traefik
    
    %% Enrutamiento Traefik
    Traefik -->|":5678"| n8n
    Traefik -->|":4000"| LiteLLM
    Traefik -->|":15672"| RabbitMQ
    Traefik -->|":3000"| Grafana
    
    %% Conexiones desde n8n
    n8n -.->|"Publica/Consume"| RabbitMQ
    n8n -.->|"Guarda/Lee Estado"| Postgres
    n8n -.->|"Llama a IA"| LiteLLM
    n8n -.->|"Búsqueda Vectorial"| Qdrant
    
    %% Conexiones desde LiteLLM
    LiteLLM -.->|"Caché de Prompts"| Redis
    LiteLLM -.->|"Almacena Modelos"| Postgres
    
    %% Observabilidad
    Traefik ==>|"Envía Trazas (gRPC)"| OTel
    n8n ==>|"Envía Trazas"| OTel
    LiteLLM ==>|"Envía Trazas"| OTel
    
    OTel ==>|"Trazas Export"| Jaeger
    OTel ==>|"Métricas Export"| Prometheus
    Prometheus ==>|"Lee Metrics"| Grafana
    Jaeger ==>|"Visualiza Trazas"| Grafana
```

---

## 2. Descripción de Componentes

### 🚪 Puerta de Enlace (API Gateway)
*   **Traefik (`cerebro-traefik`)**: Actúa como el único punto de entrada (reverse proxy). Se encarga del enrutamiento dinámico basado en nombres de dominio (`*.localhost`), *rate limiting* para proteger la infraestructura, y generación inicial del `Trace-ID` mediante OpenTelemetry para hacer seguimiento a la petición en todo el clúster.

### ⚙️ Motores Core
*   **n8n (`cerebro-n8n`)**: El "cerebro" orquestador. Define flujos de trabajo (*workflows*) visuales. Recibe notificaciones webhooks, consume URLs desde RabbitMQ, realiza scraping y orquesta los pasos ordenando al LLM que procese la información, para luego inyectar los resultados en PostgreSQL y los vectores en Qdrant.
*   **LiteLLM (`cerebro-litellm`)**: Actúa como capa de abstracción para modelos de IA. Recibe peticiones de n8n y decide internamente a qué LLM llamar (OpenAI, Anthropic, o Local). Implementa *Fallback* (si OpenAI cae, intenta con Anthropic sin afectar al sistema), usa *Circuit Breakers* y guarda peticiones comunes en caché de Redis para ahorrar tokens.

### 💾 Almacenamiento, Estado y Eventos
*   **PostgreSQL (`cerebro-postgres`)**: Centro de la verdad. Guarda los metadatos de los recursos, la tabla del patrón *Outbox* para mantener consistencia eventual de eventos, y el histórico semántico relacional entre recursos (grafología base). Incluye políticas RLS (Row-Level Security) para aislamiento multi-tenant.
*   **Redis (`cerebro-redis`)**: Base de datos en memoria hiper-rápida. Evita en tiempo real que se capturen URLs duplicadas (mediante un Bloom Filter), guarda y recupera contextos de sesiones de chats interactivas, y provee caché en sub-milisegundos al gateway de IA.
*   **RabbitMQ (`cerebro-rabbitmq`)**: Bus de mensajes de alta resiliencia. Mantiene colas de extracción de información. Si un sistema de origen o red falla, RabbitMQ reintenta o mueve el trabajo a una "Dead Letter Queue" (DLQ) mitigando fallos silenciosos.
*   **Qdrant (`cerebro-qdrant`)**: Motor de búsqueda vectorial para recuperación híbrida y *Retrieval-Augmented Generation* (RAG). Almacena los "embeddings" que el LLM genera. Aislado lógicamente mediantes payloads de `tenant_id` y preparado para *Similitud del Coseno*.

### 🔭 Observabilidad de Infraestructura
*   **OTel Collector (`cerebro-otel`)**: Recolector central que unifica *Traces* (rastreo) y *Metrics* (Métricas) de todo el sistema.
*   **Prometheus (`cerebro-prometheus`)**: Monitoriza activamente (mediante *scraping*) la salud, consumo de recursos y estado interno de todos los microservicios usando exportadores.
*   **Jaeger (`cerebro-jaeger`)**: Motor de *Distributed Tracing*. Permite auditar el ciclo de vida o viaje completo de una URL ("De Web a Base de Datos"). 
*   **Grafana (`cerebro-grafana`)**: Cuadros de mando unificados. Permite previsualizar atascos en RabbitMQ u OpenTemeletry.

---

## 3. Flujos de Trabajo Principales (Workflows)

### 3.1. Flujo de Ingesta Asíncrona (El Viaje del Dato)

Este esquema demuestra cómo el sistema absorbe picos masivos de entrada de información de forma controlada y la indexa tanto estructurada como semánticamente.

```mermaid
sequenceDiagram
    participant U as Usuario/Bot
    participant API as Traefik Gateway
    participant MQ as RabbitMQ
    participant W as n8n Worker
    participant LLM as LiteLLM (IA)
    participant PG as PostgreSQL
    participant QD as Qdrant (Vector)

    U->>API: 1. POST /webhook (Pasa URL nueva)
    API->>MQ: 2. Encola en "q.url.ingesta" (ACK rápido)
    MQ-->>U: 3. "Enlace capturado" (ms latency)
    
    Note over MQ, W: Procesamiento Offline
    
    W->>MQ: 4. Consume evento de URL
    W->>W: 5. Scraping / Extracción limpia
    W->>LLM: 6. Extraer Tags, Resumen y Estructura
    LLM-->>W: 7. JSON Estructurado
    W->>PG: 8. Insertar Recurso en SQL (Outbox = Pendiente)
    W->>LLM: 9. Solicitar Embeddings del texto
    LLM-->>W: 10. Vector [0.03, 0.45, ...]
    W->>QD: 11. Inyectar Vector + tenant_id
    W->>PG: 12. Marcar evento Outbox como "Procesado"
```

### 3.2. Curación Nocturna y Eliminación (Cost-Efficiency)

Un proceso que ejecuta n8n programado (cron) e interactúa solo con SQL para marcar elementos expirados a un costo nulo en lugar de usar Inteligencia Artificial para auditar toda la base a lo bruto.

```mermaid
sequenceDiagram
    participant Cron as Cron (n8n)
    participant PG as PostgreSQL
    
    Cron->>PG: 1. SELECT * FROM recursos WHERE estado='activo' AND fecha_caducidad < NOW()
    PG-->>Cron: 2. Devuelve Lista de UUIDs Vencidos
    Cron->>PG: 3. UPDATE recursos SET estado='cuarentena' WHERE id IN (...)
    Note over Cron: Recursos aislados, vector intacto hasta<br/> que el usuario vacíe la basura
```

### 3.3. Rutado Semántico Inteligente y RAG Híbrido

Cuando el usuario pregunta a la base a través de una interfaz o dashboard.

```mermaid
sequenceDiagram
    participant U as Dashboard
    participant API as Traefik
    participant Redis as Redis (Caché/Estado)
    participant LLM as LiteLLM
    participant QD as Qdrant
    
    U->>API: 1. Pregunta: "Resume los enlaces web3"
    API->>Redis: 2. Recuperar historial local de sesión
    Redis-->>API: 3. (Sliding Context Limitado)
    API->>LLM: 4. Genera embedding de la pregunta
    LLM-->>API: 5. Vector Semántico
    API->>QD: 6. Búsqueda Vectorial Coseno > 0.85
    QD-->>API: 7. Documentos Top-K Similares
    API->>LLM: 8. Prompt(Contexto RAG + Pregunta)
    Note over LLM: LiteLLM revisa si esta query <br/>está en la caché de Redis
    LLM-->>U: 9. Respuesta generada
```

---

## 4. Estrategia de Persistencia y Seguridad

*   **Volúmenes Docker:** Se aplican Docker Volumes estándar manejados localmente. Los datos clave de Prometheus, PostgreSQL, Qdrant y Redis garantizan durabilidad incluso tras demoler y relanzar contenedores (`docker compose down && docker compose up -d`).
*   **Permisología Multi-tenant:** Una consulta originada para el entorno X es adjuntada internamente con el `tenant_id` que filtra filas de SQL y sub-índices (payloads) de vectores Qdrant; un pilar innegociable *Security by Design*.
*   **Healthchecks Proactivos:** En el `docker-compose.yml`, los *healthchecks* evalúan internamente la conectividad real y dependencias. `LiteLLM` no iniciará procesamiento si PostgreSQL o Redis no están operacionales (mecanismo `depends_on: condition: service_healthy`).
