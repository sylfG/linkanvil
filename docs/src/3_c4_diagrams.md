# 🖼️ Documentación Visual y Diagramas C4 — LinkAnvil

Este documento provee la notación visual técnica bajo el estándar C4 Model, detallando la interacción de contenedores y el flujo distribuido de la arquitectura tolerante a fallos.

---

## Nivel 1: Diagrama de Contexto (Context Diagram)
>
> Muestra cómo el LinkAnvil encaja en el ecosistema superior, las interacciones con el usuario humano y sistemas de terceros.

```mermaid
C4Context
    title Diagrama de Contexto del Sistema - LinkAnvil
    
    Person(usuario, "Usuario (Dueño)", "Interactúa para capturar enlaces, visualizar métricas y dialogar con su propia base de conocimiento híbrida.")
    
    System(cerebro, "LinkAnvil", "Filtra, ingesta, vectoriza, y provee respuestas RAG sobre conocimiento estructurado localmente.")
    
    System_Ext(telegram, "Telegram API", "Canal omnicanal secundario para enviar URLs y reanudar sesiones del chatbot.")
    System_Ext(fuentes, "Fuentes de Datos Web", "Páginas web, APIs, y SPAs de donde el sistema raspa el contenido (Scraping).")
    System_Ext(llms, "Modelos de Lenguaje (LLMs)", "APIs externas (OpenAI, Anthropic, locales) usadas como motores de razonamiento sin acoplamiento.")
    
    Rel(usuario, cerebro, "Captura información y consulta el panel/chat", "HTTPS/WSS")
    Rel(usuario, telegram, "Envía mensajes a su bot personal")
    Rel(telegram, cerebro, "Redirige peticiones webhooks entrantes", "HTTPS")
    Rel(cerebro, fuentes, "Extrae contenido de las URLs asincrónicamente", "HTTPS/Scrapling")
    Rel(cerebro, llms, "Delega resúmenes y extracción bajo Zero-Defect", "HTTPS/REST")
```

---

## Nivel 2: Diagrama de Contenedores (Container Diagram)
>
> Detalla las piezas principales del software dentro de la red aislada `cerebro-net` y sus responsabilidades (El Recolector, El Analista, La Memoria, etc.).

```mermaid
C4Container
    title Diagrama de Contenedores - Arquitectura Interna Event-Driven
    
    Person(usuario, "Usuario")
    System_Ext(telegram, "Telegram Bot")
    System_Ext(llms, "LLM Providers")
    
    Container_Boundary(cerebro_net, "Red Virtual Segura (cerebro-net)") {
        Container(gateway, "API Gateway", "Traefik", "Termina SSL, limita tráfico, rutea y estampa Trace IDs.")
        
        Container(n8n, "Orquestador Workflow", "n8n (Node.js)", "Ejecuta estrategias de scraping, encola mensajes y centraliza flujos lógicos.")
        Container(litellm, "LLM Gateway", "LiteLLM", "Proxy agnóstico inter-proveedor. Controla Fallbacks, Cache y fuerza salidas Zod JSON.")
        
        ContainerDb(redis, "Caché Dual y Bloom Filter", "Redis", "Resuelve la deduplicación de URLs <1ms y almacena persistencia de sesiones de chat (Sliding Window).")
        ContainerDb(rabbitmq, "Cola de Ingesta (Bus)", "RabbitMQ", "Desacopla la extracción masiva y aloja la DLQ para fallos crónicos.")
        
        ContainerDb(postgres, "Verdad Relacional y Outbox", "PostgreSQL", "Aisla la tenencia (RLS) y asienta los metadatos y grafos estructurales.")
        ContainerDb(qdrant, "Base Vectorial", "Qdrant", "Almacena y busca hiper-rápidamente los embeddings segmentados por tenant_id.")
    }
    
    Rel(usuario, gateway, "Entra por dashboard web", "HTTPS")
    Rel(telegram, gateway, "Envía Webhooks al sistema", "HTTPS")
    
    Rel(gateway, n8n, "Rutea comandos principales")
    Rel(gateway, litellm, "Rutea al motor AI")
    
    Rel(n8n, redis, "Check sub-milisegundo de URL nueva")
    Rel(n8n, rabbitmq, "Publica eventos de análisis a colar")
    Rel(rabbitmq, n8n, "Consume cola para scraping pasivo")
    
    Rel(n8n, litellm, "Demanda extracción JSON estructurada")
    Rel(litellm, llms, "Petición fallback autorizada", "HTTPS")
    
    Rel(n8n, postgres, "Inserta/Lee metadata y aplica Outbox")
    Rel(n8n, qdrant, "Deriva o Recupera vectores semánticos")
```

---

## Diagrama de Flujo: Ingesta Asíncrona (Dual-Write Prevention)
>
> Detalle del patrón Outbox para la indexación cruzada y resiliente de datos provenientes del orquestador.

```mermaid
sequenceDiagram
    autonumber
    actor Usuario
    participant Traefik as API Gateway
    participant n8n as Orquestador
    participant Redis as Filtro Bloom (Redis)
    participant RMQ as RabbitMQ (Ingesta)
    participant Lite as LiteLLM (Gateway)
    participant PG as PostgreSQL (Outbox)
    participant Qdrant as Qdrant (Base Vectorial)

    Usuario->>Traefik: Guarda URL nueva
    Traefik->>n8n: Enruta (Añade Trace-ID OTel)
    n8n->>Redis: Check Colisión URL (<1ms)
    
    alt Existe colisión
        Redis-->>n8n: True
        n8n-->>Usuario: "Caché Hit: Rechazado (Ya existe)" 
    else URL Inédita
        Redis-->>n8n: False
        n8n->>RMQ: Publica Mensaje "Nueva URL"
        n8n-->>Usuario: "202 Accepted: Ingestando asíncronamente"
        
        RMQ-->>n8n: Worker consume para Scraping
        n8n->>Lite: "Analiza y formatea (Zod/JSON)"
        Lite-->>n8n: Retorna Metadatos JSON (Tags, Resumen, Volatilidad)
        
        Note right of n8n: Fase Patrón Outbox
        n8n->>PG: Transacción SQL: Guarda recursos + Estado en 'Outbox'
        PG-->>n8n: OK
        
        n8n->>Lite: "Calcula Vector/Embedding"
        Lite-->>n8n: Vector numérico
        n8n->>Qdrant: Guarda Embedding con tenant_id
        
        n8n->>PG: Actualiza Outbox a "Procesado"
    end
```

---

## Diagrama de Flujo: Exportaci�n de B�veda Obsidian (Vault.zip)
>
> Detalle del proceso de exportaci�n estructurada en formato ZIP con enlaces bidireccionales y cach� din�mico (hot.md).

`mermaid
sequenceDiagram
    autonumber
    actor Usuario
    participant Traefik as API Gateway
    participant Exporter as VaultExporter
    participant PG as PostgreSQL
    participant Mem as Memoria (ZIP)

    Usuario->>Traefik: GET /export/vault
    Traefik->>Exporter: Inicia generaci�n
    
    Exporter->>PG: Extrae Nodos, Aristas e Historial
    PG-->>Exporter: SQL Relacional (filtrado por tenant_id)
    
    Exporter->>Mem: Escribe raw/ y CLAUDE.md
    Exporter->>Mem: Escribe wiki/hot.md (Cach� RAG)
    
    loop Translaci�n de Grafo
        Exporter->>Exporter: Convierte aristas en enlaces [[Obsidian]]
        Exporter->>Mem: Escribe notas en wiki/
    end
    
    Exporter-->>Traefik: vault.zip (stream)
    Traefik-->>Usuario: Descarga ZIP Local
`
"@

Add-Content -Path "docs/src/2_architecture_risks.md" -Value @"

---

## 4. ADR-004: Offline-First LLM Wiki Export (Markdown/Obsidian)

**Contexto**: El usuario necesita acceso a su base de conocimiento incluso si la infraestructura Docker est� apagada.
**Decisión**: Un motor de exportación dinámico y seguro que traduce la base relacional/vectorial a archivos Markdown anidados (`raw/`, `wiki/`) compatibles nativamente con Obsidian, rellenando los YAML Frontmatter con el rastro del LLM y traduciendo aristas a enlaces `[[bidireccionales]]`. Todo el empaquetado del archivo `.zip` se realiza **completamente en memoria RAM** y se envía en streaming directo (on-the-fly) al navegador del usuario. No se crea ningún estado intermedio, carpeta temporal, ni archivo remanente en el almacenamiento de disco de nuestro servidor maestro, sellando completamente la privacidad multi-tenant.
**Consecuencias**: Permite control soberano total de la informaci�n (Cero Vendor-Lock In) pero requiere tareas peri�dicas de exportaci�n delta para actualizar la b�veda.
