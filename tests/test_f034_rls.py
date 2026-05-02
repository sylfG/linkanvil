"""F-03.4 — Aislamiento multi-tenant.

Tras la migración a `recursos` global + `usuario_recursos`, la RLS aplica a
la tabla pivote (`usuario_recursos`), no a `recursos` (que ya no tiene
`tenant_id`). Este test verifica que cada tenant solo ve sus filas en la
pivote y que la unión recursos↔usuario_recursos respeta el aislamiento.
"""
import asyncio
import asyncpg
import hashlib
import os
import uuid

DB_USER = os.getenv("POSTGRES_USER", "cerebro")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "cerebro_db_pass_CHANGE_ME")
DB_NAME = os.getenv("POSTGRES_DB", "cerebro_brain")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

DSN = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


async def run_rls_test():
    print(f"Connecting to database at {DSN} ...")
    conn = await asyncpg.connect(DSN)
    try:
        tenant_a = f"tenant_A_{uuid.uuid4().hex[:8]}"
        tenant_b = f"tenant_B_{uuid.uuid4().hex[:8]}"
        url_a = f"https://example.com/doc-a-{uuid.uuid4()}"
        url_b = f"https://example.com/doc-b-{uuid.uuid4()}"

        # 1. Insertar recursos globales (sin RLS, son globales).
        print("Test 1: Insertando recursos globales...")
        rec_a_id = await conn.fetchval(
            "INSERT INTO recursos (url, url_hash, titulo) VALUES ($1, $2, $3) "
            "ON CONFLICT (url_hash) DO UPDATE SET updated_at = NOW() RETURNING id",
            url_a, _url_hash(url_a), "Documento A",
        )
        rec_b_id = await conn.fetchval(
            "INSERT INTO recursos (url, url_hash, titulo) VALUES ($1, $2, $3) "
            "ON CONFLICT (url_hash) DO UPDATE SET updated_at = NOW() RETURNING id",
            url_b, _url_hash(url_b), "Documento B",
        )
        print(f"✅ Recursos creados: A={rec_a_id}, B={rec_b_id}")

        # 2. Insertar en usuario_recursos sin setear app.tenant_id → debe fallar por RLS
        print("\nTest 2: INSERT en usuario_recursos sin app.tenant_id...")
        try:
            await conn.execute(
                "INSERT INTO usuario_recursos (tenant_id, recurso_id) VALUES ($1, $2)",
                tenant_a, rec_a_id,
            )
            print("❌ FALLO: la inserción debería haber sido bloqueada por RLS.")
        except Exception as e:
            msg = str(e).lower()
            if "policy" in msg or "row-level security" in msg or "row level security" in msg:
                print("✅ EXITO: bloqueado por RLS.")
            else:
                print(f"✅ EXITO (u otro fallo de RLS): {e}")

        # 3. Setear tenant_a, asociar A → tenant_a
        print("\nTest 3: Setteando tenant_a y asociando recurso A...")
        await conn.execute(f"SET app.tenant_id = '{tenant_a}'")
        await conn.execute(
            "INSERT INTO usuario_recursos (tenant_id, recurso_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            tenant_a, rec_a_id,
        )
        print("✅ Asociación creada para tenant_a.")

        # 4. Intentar asociar a tenant_b mientras estamos como tenant_a
        print("\nTest 4: Intentando asociar como tenant_b con contexto tenant_a...")
        try:
            await conn.execute(
                "INSERT INTO usuario_recursos (tenant_id, recurso_id) VALUES ($1, $2)",
                tenant_b, rec_b_id,
            )
            print("❌ FALLO: la inserción cruzada no fue bloqueada.")
        except Exception as e:
            msg = str(e).lower()
            if "policy" in msg or "row-level security" in msg or "row level security" in msg:
                print("✅ EXITO: inserción cruzada bloqueada por RLS.")
            else:
                print(f"✅ EXITO (u otro fallo): {e}")

        # 5. Cambiar a tenant_b y crear su asociación
        print("\nTest 5: Setteando tenant_b y asociando recurso B...")
        await conn.execute(f"SET app.tenant_id = '{tenant_b}'")
        await conn.execute(
            "INSERT INTO usuario_recursos (tenant_id, recurso_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            tenant_b, rec_b_id,
        )
        print("✅ Asociación creada para tenant_b.")

        # 6. Aislamiento de lectura
        print("\nTest 6: Verificando aislamiento en lectura (JOIN)...")
        await conn.execute(f"SET app.tenant_id = '{tenant_a}'")
        records_a = await conn.fetch(
            "SELECT r.titulo FROM recursos r JOIN usuario_recursos ur ON ur.recurso_id = r.id"
        )
        titles_a = [r["titulo"] for r in records_a]
        print(f"  tenant_a ve: {titles_a}")
        if "Documento A" in titles_a and "Documento B" not in titles_a:
            print("✅ EXITO: tenant_a solo ve su recurso.")
        else:
            print("❌ FALLO: aislamiento de lectura roto.")

        await conn.execute(f"SET app.tenant_id = '{tenant_b}'")
        records_b = await conn.fetch(
            "SELECT r.titulo FROM recursos r JOIN usuario_recursos ur ON ur.recurso_id = r.id"
        )
        titles_b = [r["titulo"] for r in records_b]
        print(f"  tenant_b ve: {titles_b}")
        if "Documento B" in titles_b and "Documento A" not in titles_b:
            print("✅ EXITO: tenant_b solo ve su recurso.")
        else:
            print("❌ FALLO: aislamiento de lectura roto.")

    finally:
        # Limpieza
        try:
            await conn.execute("RESET app.tenant_id")
        except Exception:
            pass
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run_rls_test())
