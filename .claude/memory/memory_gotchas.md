---
name: gotchas-linkanvil
description: Trampas técnicas conocidas en linkanvil que no son obvias al leer el código
type: project
---

Trampas técnicas de linkanvil confirmadas en producción. Cada una ha causado un bug real.

**Why:** Estas decisiones no están documentadas en el código — son invariantes implícitas del sistema que un agente nuevo no puede deducir solo leyendo los archivos.

**How to apply:** Revisar esta lista antes de modificar scraper, embedder, o cualquier lógica de similitud/chunking.

---

## 1. NVIDIA embedding: límite duro de 512 tokens

`nv-embedqa-e5-v5` trunca silenciosamente inputs > 512 tokens. 512 tokens ≈ 1200-1300 chars en texto mixto.
`_chunk_text(target_chars=1200)` — **nunca aumentar sin cambiar el modelo**.

## 2. grafo_relaciones.similitud_check

La similitud coseno puede devolver `1.0000002` por float precision.
La tabla tiene `CHECK (similitud BETWEEN 0 AND 1)`.
Siempre: `min(similitud, 1.0)` antes de cualquier INSERT en `grafo_relaciones`.

## 3. Queue q.recurso.embedder tiene x-dead-letter-exchange

Si se declara la queue sin ese argumento, RabbitMQ lanza `ChannelPreconditionFailed`.
**Siempre usar `passive=True`** en scripts externos que declaren esta queue.

## 4. contenido IS NULL no es un error

Recursos de URLs con paywall (Medium, etc.) tienen `contenido IS NULL` en `cerebro.recursos`.
Se indexan con doc-level vector pero sin RAG chunks — comportamiento esperado.

## 5. Texto scrapeado usa \n simples, no \n\n

`_html_to_clean_text()` produce texto con `\n` simples entre líneas.
El chunker debe usar `re.split(r"\n+", text)`, no `re.split(r"\n{2,}", text)`.

## 6. Git: cuenta sylfG en el servidor

Commits en linkanvil (192.168.1.19) van con `sylfG` / `silviagandia@gmail.com`.
PAT en `~/.git-credentials` del servidor. No confundir con la cuenta personal del desarrollador.

## 7. Reused path para URLs ya indexadas globalmente

Si una URL ya existe en `cerebro.recursos`, el embedder usa `reused=True`:
copia el vector doc-level y clona chunks para el nuevo tenant sin re-scrapear.
El campo `contenido` en el payload del mensaje puede ir vacío (`""`) — el embedder lo toma de PG.
