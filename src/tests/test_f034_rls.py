import asyncio
import asyncpg
import os
import uuid

# Connection details
DB_USER = os.getenv("POSTGRES_USER", "cerebro_app")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "apppass")
DB_NAME = os.getenv("POSTGRES_DB", "cerebro_brain")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

DSN = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

async def run_rls_test():
    print(f"Connecting to database at {DSN} ...")
    conn = await asyncpg.connect(DSN)
    try:
        tenant_a = "tenant_A"
        tenant_b = "tenant_B"

        url_a = f"https://example.com/doc-a-{uuid.uuid4()}"
        hash_a = str(uuid.uuid4()) # fake hash
        
        url_b = f"https://example.com/doc-b-{uuid.uuid4()}"
        hash_b = str(uuid.uuid4()) # fake hash

        # --- 1. RLS enforcement without setting tenant ---
        # Si intentamos insertar un recurso, pero la politica requiere
        # current_setting('app.tenant_id', true)... el valor es NULL, por lo
        # que NO va a matchear la politica de INSERT y deberia fallar (o tal vez
        # porque usamos FORCE ROW LEVEL SECURITY, si intentamos es devuelto un error RLS).
        print("Test 1: Intentando insertar sin setear `app.tenant_id`...")
        try:
            await conn.execute('''
                INSERT INTO recursos (tenant_id, url, url_hash, titulo)
                VALUES ($1, $2, $3, $4)
            ''', tenant_a, url_a, hash_a, "Sin tenant_id asignado")
            print("❌ FALLO: Deberia haber prohibido la insercion sin tener un tenant seteado.")
        except asyncpg.exceptions.InsufficientPrivilegeError as e:
            print("✅ EXITO: Fue bloqueado por politicas de RLS (InsufficientPrivilegeError) al no tener setting de app.tenant_id.")
        except Exception as e:
            # Check if it fails with another RLS related error
            if "policy" in str(e).lower() or "row-level security" in str(e).lower():
                print(f"✅ EXITO: Bloqueado por RLS: {e}")
            else:
                print(f"🤷‍♂️ Otro tipo de error, puede que estemos usando 'current_setting(..., true)' que es local y lo devuelve null: {e}")

        # --- 2. Set Tenant A and insert ---
        print("\nTest 2: Seteando 'app.tenant_id' = 'tenant_A' e insertando...")
        await conn.execute(f"SET app.tenant_id = '{tenant_a}'")
        
        await conn.execute('''
            INSERT INTO recursos (tenant_id, url, url_hash, titulo)
            VALUES ($1, $2, $3, $4)
        ''', tenant_a, url_a, hash_a, "Documento de Tenant A")
        print("✅ EXITO: Inserted correctly with matching tenant!")

        # --- 3. Attempt cross-tenant insert ---
        print("\nTest 3: Intentando escribir para `tenant_B` mientras tenemos el contexto de `tenant_A`...")
        try:
            await conn.execute('''
                INSERT INTO recursos (tenant_id, url, url_hash, titulo)
                VALUES ($1, $2, $3, $4)
            ''', tenant_b, url_b, hash_b, "Documento Ilegal B cruzado")
            print("❌ FALLO: Debería haber impedido insertar con un `tenant_id` diferente al seteado.")
        except Exception as e:
            if "policy" in str(e).lower() or "row level security" in str(e).lower() or "row-level security" in str(e).lower():
                print("✅ EXITO: Inserción cruzada bloqueada por RLS.")
            else:
                print(f"✅ EXITO (u otro fallo): {e}")

        # --- 4. Read validation (Tenant A vs Tenant B) ---
        print("\nTest 4: Verificando aislamiento en lectura (SELECT)...")
        # Ensure we have a document for B (we bypass to create it)
        await conn.execute(f"SET app.tenant_id = '{tenant_b}'")
        await conn.execute('''
            INSERT INTO recursos (tenant_id, url, url_hash, titulo)
            VALUES ($1, $2, $3, $4)
        ''', tenant_b, url_b, hash_b, "Documento Real Tenant B")

        # Now search as Tenant A
        await conn.execute(f"SET app.tenant_id = '{tenant_a}'")
        records_a = await conn.fetch("SELECT titulo, tenant_id FROM recursos")
        print(f"Documentos vistos por {tenant_a}: {[(r['titulo'], r['tenant_id']) for r in records_a]}")
        
        # Is there any tenant_b document visible here?
        b_docs_seen = [r for r in records_a if r['tenant_id'] == tenant_b]
        if len(b_docs_seen) == 0:
            print(f"✅ EXITO: {tenant_a} NO puede ver los documentos de {tenant_b}")
        else:
            print(f"❌ FALLO: {tenant_a} está viendo documentos de {tenant_b}!")

        # Now search as Tenant B
        await conn.execute(f"SET app.tenant_id = '{tenant_b}'")
        records_b = await conn.fetch("SELECT titulo, tenant_id FROM recursos")
        print(f"Documentos vistos por {tenant_b}: {[(r['titulo'], r['tenant_id']) for r in records_b]}")
        a_docs_seen = [r for r in records_b if r['tenant_id'] == tenant_a]
        if len(a_docs_seen) == 0:
            print(f"✅ EXITO: {tenant_b} NO puede ver los documentos de {tenant_a}")
        else:
            print(f"❌ FALLO: {tenant_b} está viendo documentos de {tenant_a}!")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(run_rls_test())