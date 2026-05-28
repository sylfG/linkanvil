"""Helper compartido para calcular la decisión de auditoría per-tenant.

Migración 0012 separó la decisión per-tenant del recurso global. Antes
la lógica vivía inline en `save_with_outbox`; ahora también la necesita
el fast-path del scraper (`src/scraper/worker.py`) cuando reusa un
recurso global para un tenant que aún no lo tiene linkeado. Mantenerlo
en un módulo aparte evita ciclos de import entre db, scraper y el
audit_cron.

Convenciones:
- `today` se pasa por parámetro para tests deterministas. Si es None,
  se usa `datetime.utcnow().date()`.
- La policy es el JSONB de `usuarios.audit_policy` (6 keys: combinaciones
  de {evento|referencia}_pasado_{alto|medio|nulo} → activo|cuarentena|expirado).
- Para `temporal_class='evergreen'` o contenido no-pasado, la decisión
  cae al default: `estado='procesando'`, sin marcas de quarantine. El
  embedder transiciona después a 'activo' o 'expirado' según el flag
  `auto_archive_pending`.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Optional

GRACE_PERIOD_DAYS = int(os.getenv("OBSOLESCENCE_GRACE_DAYS", "30"))
DEFAULT_USEFUL_LIFE_DAYS = int(os.getenv("DEFAULT_USEFUL_LIFE_DAYS", "30"))


def compute_audit_decision(
    *,
    temporal_class: str,
    valor_archivistico: str,
    fecha_evento: Optional[date],
    useful_life_days: Optional[int],
    policy: dict,
    today: Optional[date] = None,
) -> dict:
    """Devuelve la decisión per-tenant a aplicar al recurso.

    Returns:
        dict con las 5 columnas a poblar en `usuario_recursos`:
          - estado: 'procesando' | 'activo' | 'cuarentena' | 'expirado'
            (NB: tras esta función, el caller persiste 'procesando' y
             el embedder lo termina; 'cuarentena'/'expirado' los pone
             ya esta función para casos policy-driven)
          - quarantine_reason: 'evento_pasado' | None
          - quarantine_grace_until: date | None
          - quarantined_at: datetime | None
          - auto_archive_pending: bool
          - fecha_caducidad: date | None
    """
    if today is None:
        today = datetime.utcnow().date()

    # Normalización defensiva (mismo bloque que estaba inline en
    # save_with_outbox: defaults seguros si el LLM falló).
    if temporal_class not in ("evento", "referencia", "evergreen"):
        temporal_class = "evento"
    if valor_archivistico not in ("alto", "medio", "nulo"):
        valor_archivistico = "medio"

    # fecha_caducidad: solo aplica a temporal_class='evento' futuro.
    # Para 'referencia' y 'evergreen', o cualquier 'evento' con fecha
    # pasada, queda NULL.
    if temporal_class == "evento":
        if useful_life_days is None:
            useful_life_days = DEFAULT_USEFUL_LIFE_DAYS
        fecha_caducidad: Optional[date] = today + timedelta(days=useful_life_days)
    else:
        fecha_caducidad = None

    event_past = fecha_evento is not None and fecha_evento <= today
    caducidad_past = fecha_caducidad is not None and fecha_caducidad <= today
    pasado = event_past or caducidad_past

    estado = "procesando"
    quarantine_reason: Optional[str] = None
    quarantine_grace_until: Optional[date] = None
    quarantined_at: Optional[datetime] = None
    auto_archive_pending = False

    if temporal_class != "evergreen" and pasado:
        if temporal_class == "evento":
            key = f"evento_pasado_{valor_archivistico}"
        else:
            key = f"referencia_pasada_{valor_archivistico}"
        decision = policy.get(key, "cuarentena")
        # Decisiones sobre "pasado" siempre limpian fecha_caducidad: el
        # ciclo de caducidad ya no aplica una vez categorizado como
        # histórico/archivable.
        fecha_caducidad = None
        if decision == "cuarentena":
            estado = "cuarentena"
            quarantine_reason = "evento_pasado"
            quarantine_grace_until = today + timedelta(days=GRACE_PERIOD_DAYS)
            quarantined_at = datetime.utcnow()
        elif decision == "expirado":
            # Auto-archive: el recurso pasa por el embedder igualmente
            # (para tener chunks indexados en Qdrant, accesibles vía
            # Archivo ON en chat) pero al terminar el embedder lo
            # transiciona a 'expirado' en lugar de 'activo'.
            auto_archive_pending = True
        # decision == "activo" → no-op, queda procesando→activo

    return {
        "estado": estado,
        "quarantine_reason": quarantine_reason,
        "quarantine_grace_until": quarantine_grace_until,
        "quarantined_at": quarantined_at,
        "auto_archive_pending": auto_archive_pending,
        "fecha_caducidad": fecha_caducidad,
    }
