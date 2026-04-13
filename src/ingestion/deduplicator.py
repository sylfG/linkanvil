import sys
import logging
from typing import Optional, Callable
import redis

logger = logging.getLogger(__name__)

class RedisDeduplicator:
    """
    Filtro Deduplicador en Tiempo Real basado en Bloom Filters (RedisBloom).
    Requirements:
    - F-01.1: Evitar múltiples ingestas idénticas.
    - Trace ID & Tenant_ID isolation.
    - Menos de 1ms de latencia (via redis operations).
    - Tolerancia a fallos: Deriva a DLQ / Fallback si Redis cae.
    """
    
    def __init__(self, 
                 redis_client: redis.Redis, 
                 dlq_callback: Optional[Callable[[str, str, str, Exception], None]] = None):
        """
        :param redis_client: Instancia de Redis configurada (debe soportar RedisBloom).
        :param dlq_callback: Función a invocar cuando ocurre un fallo crítico al interactuar con Redis. 
                             Firma: func(item, tenant_id, trace_id, exception)
        """
        self.redis = redis_client
        self.dlq_callback = dlq_callback
        self.default_error_rate = 0.001
        self.default_capacity = 1000000

    def _get_bloom_key(self, tenant_id: str) -> str:
        """Aislamiento multi-tenant por llave."""
        return f"bf:tenant:{tenant_id}:ingestion"

    def _ensure_bloom_filter(self, key: str, trace_id: str) -> None:
        """Nos aseguramos de que el filtro Bloom existe, si no, lo reservamos con la capacidad deseada."""
        try:
            # check si existe
            if not self.redis.exists(key):
                # bf.reserve
                self.redis.bf().reserve(key, self.default_error_rate, self.default_capacity)
                logger.info(f"[{trace_id}] Bloom Filter creado localmente para llave: {key}")
        except redis.exceptions.ResponseError as e:
            # Si el filtro ya fue creado concurrentemente, redis.bf().reserve podría arrojar un error de que ya existe.
            # Lo ignoramos.
            if "already exists" not in str(e).lower():
                raise e
            
    def is_new_item(self, item_hash: str, tenant_id: str, trace_id: str) -> bool:
        """
        Inyecta el elemento en el Bloom Filter.
        Retorna:
        - True si es un elemento nuevo (y por tanto añadido).
        - False si ya existía (posiblemente un falso positivo con ~0.1% prob).
        - False (o lanza DLQ) si existe fallo de Redis.
        """
        key = self._get_bloom_key(tenant_id)
        
        try:
            # Intentamos asegurar que exista
            self._ensure_bloom_filter(key, trace_id)
            
            # bf.add devuelve 1 si no existía (nuevo), 0 si ya existía (duplicado)
            result = self.redis.bf().add(key, item_hash)
            
            is_new = bool(result)
            if is_new:
                logger.info(f"[{trace_id}] [TENANT:{tenant_id}] Nuevo elemento ingerido: {item_hash}")
            else:
                logger.info(f"[{trace_id}] [TENANT:{tenant_id}] Elemento DUPLICADO ignorado: {item_hash}")
                
            return is_new
            
        except (redis.exceptions.RedisError, Exception) as e:
            logger.error(f"[{trace_id}] [TENANT:{tenant_id}] Error validando duplicidad de '{item_hash}' en Redis: {str(e)}")
            
            if self.dlq_callback:
                self.dlq_callback(item_hash, tenant_id, trace_id, e)
                return False # Si se fue a la DLQ, asumimos que no continua por el Happy path normal
            
            # Fallback por defecto si no hay DLQ: "fail-closed" para no asfixiar downstream, 
            # pero depende del negocio. Asumiremos que en fallo lo dejamos pasar (fail-open)
            # para no paralizar el sistema si red cae y es crítico que se grabe algo.
            # Notar que 'Deriva a DLQ o Fallback' se atiende con dlq_callback.
            logger.warning(f"[{trace_id}] [TENANT:{tenant_id}] Fallback aplicado (fail-open), elemento admitido.")
            return True
