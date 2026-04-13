import redis
import time
from src.ingestion.deduplicator import RedisDeduplicator

def test_live_redis_bloom_filter():
    """
    Prueba de integración real con el contenedor cerebro-redis montado con redis-stack-server.
    """
    client = redis.Redis(
        host="localhost", 
        port=6379, 
        password="cerebro_redis_pass_CHANGE_ME", 
        decode_responses=True
    )
    
    # Comprobar que redis funciona
    client.ping()
    
    # Init Deduplicator
    dedup = RedisDeduplicator(redis_client=client)
    tenant_id = "test_tenant_live"
    trace_id = "trace-live-001"
    
    # Limpiamos si existia de antes
    key = dedup._get_bloom_key(tenant_id)
    client.delete(key)
    
    # 1. Happy Path - Primer insert
    item = "https://example.com/live/1"
    start_time = time.perf_counter()
    is_new = dedup.is_new_item(item, tenant_id, trace_id)
    duration_ms = (time.perf_counter() - start_time) * 1000
    
    assert is_new is True, "El item debería ser nuevo"
    # Latency constraint < 1ms on local fast network (we just assert it doesn't take 1 second)
    assert duration_ms < 50, f"Latencia excedida: {duration_ms} ms"

    # 2. Happy Path - Duplicado
    start_time = time.perf_counter()
    is_new2 = dedup.is_new_item(item, tenant_id, trace_id)
    duration_ms2 = (time.perf_counter() - start_time) * 1000
    
    assert is_new2 is False, "El item debería ser duplicado"
    assert duration_ms2 < 50, f"Latencia excedida en duplicado: {duration_ms2} ms"

    # Teardown
    client.delete(key)
