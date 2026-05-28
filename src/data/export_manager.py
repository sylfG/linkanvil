import io
import json
import zipfile
import re
from datetime import datetime, timezone
from typing import List, Dict, Any

from src.data.db import DatabaseManager


class VaultExporter:
    def __init__(self, db: DatabaseManager):
        self.db = db

    def _sanitize_filename(self, title: str) -> str:
        s = re.sub(r"[^a-zA-Z0-9_\-\s]", "", title or "untitled")
        return s.strip()[:50]

    async def fetch_resources(self, tenant_id: str) -> List[Dict[str, Any]]:
        """Recursos asociados al tenant via la pivote `usuario_recursos`.
        `created_at` es el momento en que el usuario añadió la URL a su KB."""
        if not self.db.pool:
            await self.db.connect()

        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT r.id, r.url, r.titulo, r.resumen, r.categoria, r.tags,
                       r.volatilidad, ur.estado, ur.created_at, ur.fecha_caducidad
                FROM recursos r
                JOIN usuario_recursos ur ON ur.recurso_id = r.id
                WHERE ur.tenant_id = $1
                ORDER BY ur.created_at DESC
                """,
                tenant_id,
            )
            return [dict(r) for r in rows]

    async def fetch_relations(self, tenant_id: str) -> List[Dict[str, Any]]:
        if not self.db.pool:
            await self.db.connect()

        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT recurso_origen, recurso_destino, tipo_relacion
                FROM grafo_relaciones
                WHERE tenant_id = $1
                """,
                tenant_id,
            )
            return [dict(r) for r in rows]

    async def fetch_chat_contexts(self, tenant_id: str) -> List[Dict[str, Any]]:
        if not self.db.pool:
            await self.db.connect()

        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, titulo, contexto_comprimido, ultimo_acceso
                FROM sesiones_chat
                WHERE tenant_id = $1
                ORDER BY ultimo_acceso DESC
                """,
                tenant_id,
            )
            return [dict(r) for r in rows]

    async def fetch_audit_logs(self, tenant_id: str) -> List[Dict[str, Any]]:
        if not self.db.pool:
            await self.db.connect()

        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT creado_en, agregado_tipo, agregado_id, evento_tipo, procesado
                FROM outbox_eventos
                WHERE tenant_id = $1
                ORDER BY creado_en ASC
                """,
                tenant_id,
            )
            return [dict(r) for r in rows]

    async def generate_vault_zip(self, tenant_id: str) -> bytes:
        resources = await self.fetch_resources(tenant_id)
        relations = await self.fetch_relations(tenant_id)
        sessions = await self.fetch_chat_contexts(tenant_id)
        audits = await self.fetch_audit_logs(tenant_id)

        # Pre-compute filenames for all resources
        resource_map = {}
        for res in resources:
            safe_title = self._sanitize_filename(res.get("titulo", ""))
            res_id = str(res.get("id", ""))
            if not safe_title:
                safe_title = res_id[:8]
            file_basename = f"{safe_title}_{res_id[:4]}"
            resource_map[res_id] = file_basename

        # Group relations by origen
        relations_by_origen = {}
        for rel in relations:
            origen = str(rel["recurso_origen"])
            if origen not in relations_by_origen:
                relations_by_origen[origen] = []
            relations_by_origen[origen].append(rel)

        mem_zip = io.BytesIO()
        with zipfile.ZipFile(mem_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            # --- 1. Base Structure & Seed Files ---

            # index.md
            zf.writestr(
                "index.md",
                "# Bóveda LLM Wiki\n\nAquí reside tu Segundo Cerebro Digital.\n",
            )

            # CLAUDE.md
            claude_rules = (
                "# Reglas del Agente Local\n"
                "1. No modifiques la carpeta `raw/` directamente.\n"
                "2. Explora `wiki/` para ver los conceptos compilados.\n"
                "3. Lee `wiki/hot.md` para entender el contexto anterior inmediato.\n"
            )
            zf.writestr("CLAUDE.md", claude_rules)

            # log.md (historical events)
            log_md = f"# Export Log & Audit Timeline\n\n- Fecha de Exportación: {datetime.now(timezone.utc).isoformat()}\n- Recursos Totales: {len(resources)}\n\n## Timeline de Eventos\n\n"
            for audit in audits:
                date_str = (
                    audit.get("creado_en", "").isoformat()
                    if hasattr(audit.get("creado_en", ""), "isoformat")
                    else str(audit.get("creado_en", ""))
                )
                ev_type = audit.get("evento_tipo", "unknown")
                ag_type = audit.get("agregado_tipo", "")
                ag_id = str(audit.get("agregado_id", ""))
                status = "Procesado" if audit.get("procesado") else "Pendiente"
                log_md += f"1. **[{date_str}]** `{ev_type}` sobre `{ag_type}` ({ag_id}) - *{status}*\n"
            zf.writestr("wiki/log.md", log_md)

            # hot.md (hot cache for AI)
            hot_md = "# Caché Caliente Dinámica (Hot Cache)\n\n"
            hot_md += "> Contexto de conversaciones y sesiones recientes extraídas vía Sliding Window API. Útil para reanudar el estado mental del LLM local.\n\n"
            for sess in sessions:
                s_title = sess.get("titulo") or "Sesión sin título"
                s_date = (
                    sess.get("ultimo_acceso", "").isoformat()
                    if hasattr(sess.get("ultimo_acceso", ""), "isoformat")
                    else str(sess.get("ultimo_acceso", ""))
                )
                s_ctx = sess.get("contexto_comprimido") or "*(Sin contexto disponible)*"
                hot_md += f"## {s_title}\n"
                hot_md += f"**Último acceso:** {s_date}\n\n"
                hot_md += "### Contexto Comprimido (Sliding Window)\n"
                hot_md += f"{s_ctx}\n\n---\n\n"
            zf.writestr("wiki/hot.md", hot_md)

            # --- 2. Iterate resources ---
            for res in resources:
                safe_title = self._sanitize_filename(res.get("titulo", ""))
                res_id = str(res.get("id", ""))
                if not safe_title:
                    safe_title = res_id[:8]

                file_basename = f"{safe_title}_{res_id[:4]}"

                # Format to JSON for tags
                tags = res.get("tags", "[]")
                if isinstance(tags, str):
                    try:
                        tags_list = json.loads(tags)
                    except (json.JSONDecodeError, TypeError):
                        tags_list = []
                else:
                    tags_list = tags
                tag_str = " ".join([f"#{t}" for t in tags_list])

                # Raw Text Base (textos planos originales)
                raw_content = (
                    f"URL: {res.get('url', '')}\n"
                    f"Metadata: \n"
                    f"- Categoria: {res.get('categoria', 'other')}\n"
                    f"- Estado: {res.get('estado', '')}\n\n"
                    f"{res.get('resumen', '')}"
                )
                zf.writestr(f"raw/{file_basename}.txt", raw_content)

                # Wiki Base
                cat = res.get("categoria", "other").lower()
                folder_map = {
                    "entity": "entities",
                    "entidad": "entities",
                    "person": "entities",
                    "tool": "entities",
                    "concept": "concepts",
                    "concepto": "concepts",
                    "idea": "concepts",
                }
                dest_folder = folder_map.get(cat, "sources")

                wiki_content = (
                    f"---\n"
                    f"id: {res_id}\n"
                    f"title: {res.get('titulo')}\n"
                    f"tags: {tags_list}\n"
                    f"status: {res.get('estado')}\n"
                    f"---\n\n"
                    f"# {res.get('titulo')}\n\n"
                    f"**Fuente:** {res.get('url')}\n"
                    f"**Etiquetas:** {tag_str}\n\n"
                    f"## Resumen Analítico\n"
                    f"{res.get('resumen', '')}\n\n"
                )

                # Add relations / Links for Obsidian
                rels = relations_by_origen.get(res_id, [])
                if rels:
                    wiki_content += "## Relaciones\n"
                    for rel in rels:
                        t = rel.get("tipo_relacion", "ASOCIACION_GENERAL")
                        dest_id = str(rel.get("recurso_destino", ""))
                        if dest_id in resource_map:
                            dest_name = resource_map[dest_id]
                            # Translating relations to markdown
                            # Markdown logic for F-07.2
                            if t == "CONTRADICE":
                                wiki_content += (
                                    f"> [!warning] Contradice a: [[{dest_name}]]\n"
                                )
                            elif t == "VUELVE_OBSOLETO":
                                wiki_content += f"> [!important] Vuelve obsoleto a: [[{dest_name}]]\n"
                            elif t == "OBSOLECIDO_POR":
                                wiki_content += (
                                    f"> [!error] Obsoleto por: [[{dest_name}]]\n"
                                )
                            elif t == "EXTIENDE":
                                wiki_content += (
                                    f"> [!info] Extiende a: [[{dest_name}]]\n"
                                )
                            elif t == "ES_UN":
                                wiki_content += (
                                    f"> [!info] Es un tipo de: [[{dest_name}]]\n"
                                )
                            else:
                                wiki_content += f"- Relacionado con: [[{dest_name}]]\n"

                    wiki_content += "\n"

                wiki_content += f"*(Raw data at `raw/{file_basename}.txt`)*\n"

                zf.writestr(f"wiki/{dest_folder}/{file_basename}.md", wiki_content)

        return mem_zip.getvalue()
