# Review · index · 2026-05-19

**Auditor**: docs-reality-auditor
**Doc revisado**: `docs/src/index.md`
**Áreas de código verificadas**: `docs/.vitepress/config.mts`, `docs/src/*.md`, `docker-compose.yml`
**Versión del repo**: `develop` @ `7c723f3`

## Resumen
- 1 CRITICAL, 0 HIGH, 2 MEDIUM, 0 LOW, 0 UNVERIFIED
- 0 hallazgos [CODE-BUG]
- Veredicto: **RED** (hay 1 CRITICAL — la CTA principal de la portada lleva a un path inexistente)

## Hallazgos

### [CRITICAL] CTA "Épicas y Features" enlaza a un path que no existe

- **Ubicación**: `docs/src/index.md:11`
- **Lo que dice el doc**:
  > ```yaml
  >     - theme: brand
  >       text: Épicas y Features
  >       link: /1_epics_and_features
  > ```
- **Realidad en el código**: No existe ningún archivo `docs/src/1_epics_and_features.md` en el root de `srcDir`. El único `1_epics_and_features.md` vive bajo el subdirectorio `Extractor_de_Requisitos/` (evidencia: `ls docs/src/` no contiene `1_epics_and_features.md` y `ls docs/src/Extractor_de_Requisitos/` sí lo contiene). El propio `config.mts` referencia el path correcto en el sidebar de "Extracción de requisitos" como `/Extractor_de_Requisitos/1_epics_and_features` (`docs/.vitepress/config.mts:144`). Además, `ignoreDeadLinks: true` está activado (`docs/.vitepress/config.mts:99`) por lo que el build NO falla, lo que enmascara el bug en CI — el usuario que pulse el botón principal verá un 404 en producción (GitHub Pages bajo `base: "/linkanvil/"`).
- **Cambio sugerido**:
  ```markdown
      - theme: brand
        text: Épicas y Features
        link: /Extractor_de_Requisitos/1_epics_and_features
  ```

### [MEDIUM] La CTA principal apunta al backlog en vez de a la documentación general

- **Ubicación**: `docs/src/index.md:9-11`
- **Lo que dice el doc**:
  > ```yaml
  >     - theme: brand
  >       text: Épicas y Features
  >       link: /1_epics_and_features
  > ```
- **Realidad en el código**: La nav principal del sitio (`docs/.vitepress/config.mts:118-122`) declara tres entradas: "Inicio" (`/`), "Documentación" (`/0-resumen`) y "Extracción de requisitos" (`/Extractor_de_Requisitos/`). El landing de la portada hace `brand` (CTA primaria) hacia el backlog de features en lugar de hacia el doc de entrada `/0-resumen`, que es la primera opción del sidebar "📋 Proyecto" (`config.mts:128-141`). Para un visitante nuevo lo natural es que la CTA primaria abra el resumen del proyecto y la alternativa lleve al backlog. Tal como está, la portada vende "Plataforma RAG…" y empuja al usuario directo al backlog Extractor_de_Requisitos sin pasar por el contexto. (Hallazgo de UX/coherencia, no fallo factual — por eso MEDIUM, no CRITICAL.)
- **Cambio sugerido**:
  ```markdown
  hero:
    name: "LinkAnvil"
    text: "Plataforma RAG orientada a eventos para extraer y organizar conocimiento."
    tagline: "Ingesta asíncrona, RAG híbrido multi-tenant y Zero-Defect pipeline con despliegue local."
    actions:
      - theme: brand
        text: Empezar
        link: /0-resumen
      - theme: alt
        text: Épicas y Features
        link: /Extractor_de_Requisitos/1_epics_and_features
      - theme: alt
        text: Ver en GitHub
        link: https://github.com/sylfG/linkanvil
  ```

### [MEDIUM] La portada no menciona ni enlaza el área "Documentación" que el nav promociona como primer ciudadano

- **Ubicación**: `docs/src/index.md:8-14` (sección `actions`)
- **Lo que dice el doc**:
  > Solo expone dos `actions`: "Épicas y Features" + "Ver en GitHub". Ninguna referencia visible desde la portada al árbol `0-resumen / 1-instalacion-configuracion / 2-resumen-servicios / 3-componentes / 4-arquitectura / 5-herramientas-ia / 7-prompts / 8-lifecycle / 9-ejemplo_flujo / 10-demo / 11-Glosario`.
- **Realidad en el código**: El sidebar (`docs/.vitepress/config.mts:127-142`) y el nav (`config.mts:120`) tratan `/0-resumen` y la cadena `1…11` como el corpus principal del sitio. El landing no menciona esta sección, lo que crea un gap entre lo que la nav presume (`text: "Documentación"`) y lo que la portada destaca. Ver propuesta del hallazgo anterior — añadir una `action` hacia `/0-resumen` resuelve también este gap.
- **Cambio sugerido**: ver el bloque del hallazgo MEDIUM anterior (la propuesta cubre ambos puntos).

## Aprobado sin cambios
- `index.md:5-7` "name / text / tagline" — verificado contra el stack real del repo.
- `index.md:14` `link: https://github.com/sylfG/linkanvil` — verificado contra `git config --get remote.origin.url` → `https://github.com/sylfG/linkanvil`.
- `index.md:17-19` feature "Ingesta Asíncrona Orientada a Eventos / RabbitMQ" — verificado contra `docker-compose.yml:4` ("# Servicios: Traefik · RabbitMQ · Redis · PostgreSQL · Qdrant · n8n ·") y `infra/rabbitmq/`.
- `index.md:21-23` feature "Búsqueda Vectorial Híbrida / Qdrant" — verificado contra `infra/qdrant/` y `docker-compose.yml:4`.
- `index.md:25-27` feature "Zero-Defect Pipeline / Gateway local de LLMs" — verificado contra `infra/litellm/` (LLM gateway local).
- `index.md:29-31` feature "Arquitectura Total Local / Docker Compose / PostgreSQL / Redis / Outbox" — verificado contra `docker-compose.yml:4` y `infra/postgres/`.
- `index.md:33-35` feature "Seguro por Diseño / cerebro-net / Traefik" — verificado contra `docker-compose.yml:31,81,113,145,180,212,246,281,325,368` (todos los servicios en `cerebro-net`) y `docker-compose.yml:297-335` (servicio Traefik con dashboard + middlewares ratelimit/retry).
