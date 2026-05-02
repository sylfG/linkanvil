<div align="center">
  <img src="../public/logo-light.png" alt="Logo" width="80" height="80" class="light-only">
  <img src="../public/logo-dark.png" alt="Logo" width="80" height="80" class="dark-only">


# Documento Maestro de Entrada (Contexto Fuente)

</div>
Este archivo es la entrada principal del workflow.

Objetivo:

- Recibir informacion bruta del cliente (entrevistas, conversaciones, notas, correos, actas, tickets, enlaces).
- Permitir que la IA extraiga requisitos y genere automaticamente las fases posteriores.

Regla clave:

- No escribir aqui requisitos ya procesados (no epics, no features, no backlog).
- Aqui solo se guarda contexto fuente y datos operativos minimos.

---

## Reglas de Uso

- Mantener encabezados 0 a 10 sin renombrar.
- Pegar informacion lo mas literal posible cuando venga del cliente.
- Si algo no existe, escribir: No disponible.
- Si un dato no aplica, escribir: No aplica (motivo).
- Actualizar fecha y version en cada cambio.

---

## 0. Datos Operativos del Proyecto (Obligatorio)

| Campo | Valor |
| --- | --- |
| Nombre del proyecto | LinkAnvil |
| Codigo interno (si existe) | SCA-01 |
| Fecha ultima actualizacion (YYYY-MM-DD) | 2026-04-09 |
| Responsable funcional | No disponible |
| Responsable tecnico | No disponible |
| Estado del discovery (`Borrador`, `En captura`, `Listo para extraccion IA`) | Listo para extraccion IA |

---

## 1. Contexto GitHub (Obligatorio para Fase 6)

| Campo | Valor | Ejemplo |
| --- | --- | --- |
| URL del repositorio | <https://github.com/sylfG/linkanvil> | <https://github.com/mi-org/mi-repo> |
| Repositorio (`OWNER/REPO`) | sylfG/linkanvil | mi-org/mi-repo |
| Organizacion GitHub | sylfG | mi-org |
| GitHub Project Number (numero) | 5 | 14 |
| Publicar milestones por epica (`Si` o `No`) | Si | Si |
| Vincular dependencias nativas (`Si` o `No`) | Si | Si |

Prerequisitos tecnicos (check rapido):

- gh CLI autenticado.
- jq instalado.
- GitHub Project con campo Priority (`Must`, `Should`, `Could`).

---

## 2. Inventario de Fuentes de Contexto (Obligatorio)

Anotar todas las fuentes desde las que la IA debe extraer requisitos.

| ID | Tipo de fuente | Fecha | Autor/Origen | Estado (`Pendiente`, `Procesada`) | Ubicacion o referencia |
| --- | --- | --- | --- | --- | --- |
| SRC-01 | Documento cliente | 2026-04-09 | Cliente | Procesada | docs/src/resumen.md |
| SRC-02 | Documento cliente | 2026-04-09 | Cliente | Procesada | docs/src/ARQUITECTURA.md |

Tipos sugeridos:

- Entrevista
- Conversacion
- Email
- Acta de reunion
- Documento cliente
- Ticketing
- Enlace externo

---

## 3. Contexto Bruto del Cliente (Obligatorio)

Pegar aqui contenido literal o resumido fiel del cliente.

### 3.1 Transcripciones / Conversaciones

No disponible

### 3.2 Notas de entrevistas

No disponible

### 3.3 Correos / mensajes relevantes

No disponible

### 3.4 Documentos externos y enlaces

- Resumen del Proyecto - docs/src/resumen.md - El proyecto "LinkAnvil" transforma el caos de la información en conocimiento accionable mediante una arquitectura orientada a eventos, asíncrona, descapolada y resiliente.
- Arquitectura del Sistema - docs/src/ARQUITECTURA.md - Detalla la infraestructura local basada en Docker Compose, topología de la red, los componentes desplegados (Traefik, n8n, LiteLLM, Qdrant, etc.) y los flujos de información a través del sistema.

---

## 4. Hechos Confirmados (sin derivar requisitos) (Obligatorio)

Solo hechos ya confirmados por el cliente. No inferencias.

- Hecho 1: La infraestructura local se basa en Docker Compose con una red privada "cerebro-net".
- Hecho 2: Traefik funge como API Gateway proporcionando Rate Limiting y enrutamiento dinámico.
- Hecho 3: n8n funciona como el cerebro orquestador que consume las URLs de los mensajes de la cola asíncrona de ingestión (RabbitMQ).
- Hecho 4: LiteLLM abstracta el acceso a modelos de IA, realiza llamadas a OpenAI y Anthropic mediante un Fallback automático, y devuelve JSON estructurado (Zod/Pydantic) además de realizar embeddings.
- Hecho 5: Se utiliza Qdrant para almacenar fragmentos vectoriales (embeddings) para búsqueda híbrida y RAG, aislando los entornos con 'tenant_id'.
- Hecho 6: La persistencia de hechos de sesión se realiza en PostgreSQL (relacional y estado con patrón Outbox) y Redis para cachés instantáneos sub-milisegundo.
- Hecho 7: El sistema incorpora un curador nocturno para eliminar/cuarentenan eventos obsoletos mediante evaluación de fechas y/o de volatilidad tecnológica de forma asequible.

---

## 5. Restricciones y Condicionantes Conocidos (Obligatorio)

Ejemplos: legales, presupuestarios, tecnologicos, tiempos, dependencias externas.

- Restriccion 1: El proyecto opera como un "Standalone" local en vez de dependencias acopladas a APIs pesadas como Notion/Obsidian.
- Restriccion 2: La arquitectura está implementada 100% como Orientada a Eventos; las interacciones asíncronas con colas de mensajería (RabbitMQ) y el Patrón Outbox de PostgreSQL son mandatorios para la consistencia eventual.
- Restriccion 3: Las respuestas de Inteligencia Artificial (desde LiteLLM) requieren Salidas Estructuradas Estrictas (Zero-Defect Pipeline mediante Zod/Pydantic) retornando forzosamente datos tabulares, resúmenes, entidades y fecha de ciclo de vida.
- Restriccion 4: Permisología Multi-tenant en toda la pila tecnológica (bases relacionales con RLS y vectores filtrados por 'tenant_id') para evitar cruce de información.

---

## 6. Supuestos y Huecos de Informacion (Obligatorio)

Este bloque ayuda a la IA a detectar incertidumbre antes de extraer requisitos.

| Tema | Tipo (`Supuesto` o `Dato faltante`) | Impacto (`Alto`, `Medio`, `Bajo`) | Accion para resolver |
| --- | --- | --- | --- |
| Detalle Interfaz Visual del Dashboard | Dato faltante | Medio | Solicitar bocetos para definir features front-end |
| Métricas de SLA/Latencia | Dato faltante | Bajo | Precisar en requisitos no funcionales los SLAs esperados de búsquedas híbridas |

---

## 7. Criterios de Extraccion para la IA (Obligatorio)

Definir como quieres que la IA procese las fuentes.

| Parametro | Valor |
| --- | --- |
| Idioma de salida | Español |
| Nivel de detalle esperado (`Alto`, `Medio`, `Bajo`) | Alto |
| Priorizar rapidez o exhaustividad (`Rapidez`, `Equilibrado`, `Exhaustivo`) | Exhaustivo |
| Tolerancia a inferencia (`Minima`, `Moderada`, `Alta`) | Minima |
| Enfoque principal (`Negocio`, `Tecnico`, `Mixto`) | Mixto |

Notas opcionales para el agente:

- Las épicas y features deben reflejar la arquitectura técnica distribuida definida, diferenciando bien ingesta asíncrona de procesamiento sincrónico RAG.

---

## 8. Glosario y Terminologia del Cliente (Recomendado)

Terminos de dominio para evitar interpretaciones incorrectas.

| Termino | Definicion del cliente | Sinónimos/alias |
| --- | --- | --- |
| Segundo Cerebro | Plataforma híbrida RAG (vectorial y relacional) usada para ingestar, organizar y consultar conocimiento encapsulado | SCA, Sistema |
| Patrón Outbox | Estrategia de consistencia eventual que usa PostgreSQL y RabbitMQ para guardar estado seguro y lanzar eventos posteriores a colas | Bandeja de salida |
| Zero-Defect Pipeline | Proceso de extracción IA estricto en LiteLLM donde se fuerza a que devuelva un formato JSON bajo esquemas Zod o Pydantic | Salidas estructuradas |
| Sliding Window | Límite asimétrico circular de tokens aplicado antes de enviar historiales de conversación del usuario hacia un modelo de chat para ahorrar tokens | Context window |

---

## 9. Semaforo por Fase (Control Operativo)

Actualizar solo cuando la informacion minima para una fase este lista.

| Fase | Minimo requerido | Estado (`Pendiente` o `Listo`) |
| --- | --- | --- |
| Fase 1 - Epics y Features | Bloques 0, 2, 3, 4, 6, 7 | Listo |
| Fase 2 - Arquitectura y Riesgos | Bloques 0, 3, 5, 6, 7 | Listo |
| Fase 3 - Backlog por feature | Bloques 0, 2, 3, 4, 5, 7 | Pendiente |
| Fase 4 - Diagramas C4 | Bloques 0, 3, 5, 7 | Pendiente |
| Fase 5 - Publicacion VitePress | Bloques 0, 9 y artefactos previos aprobados | Pendiente |
| Fase 6 - Subida a GitHub | Bloques 1 y backlog aprobado | Pendiente |

---

## 10. Registro de Cambios y Aprobaciones

| Fecha | Cambio realizado | Responsable | Aprobado por |
| --- | --- | --- | --- |
| 2026-04-09 | Creacion/actualizacion de contexto fuente de Arquitectura y Resumen del LinkAnvil | Asistente IA | Usuario |
