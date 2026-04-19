import os
import logging
import uuid
import asyncio
from functools import wraps

logger = logging.getLogger(__name__)

OTEL_COLLECTOR_URL = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318/v1/traces")

def configure_telemetry(service_name: str) -> bool:
    """
    Configura y unifica el propagador de traces (Trace Context)
    apuntando al OpenTelemetry Collector perimetral.
    """
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
        from opentelemetry.propagate import set_global_textmap

        resource = Resource.create(attributes={
            SERVICE_NAME: service_name,
            "environment": os.getenv("ENV", "local")
        })

        provider = TracerProvider(resource=resource)
        
        # OTLP Exporter apuntando al collector unificado
        otlp_exporter = OTLPSpanExporter(endpoint=OTEL_COLLECTOR_URL)
        
        # Prevenimos el cuello de botella enviando en batch (Latencia pre-definida)
        processor = BatchSpanProcessor(otlp_exporter)
        provider.add_span_processor(processor)

        trace.set_tracer_provider(provider)
        
        # Propagadores globales
        set_global_textmap(TraceContextTextMapPropagator())

        logger.info(f"OpenTelemetry configurado exitosamente para el servicio: {service_name} apuntando a {OTEL_COLLECTOR_URL}")
        return True
    except ImportError as e:
        logger.warning(f"Librerías de OpenTelemetry no instaladas. Fallback a trazabilidad logs: {e}")
        return False
    except Exception as e:
        logger.error(f"Fallo crítico al configurar OpenTelemetry (Fallback Edge Case): {e}")
        return False

def get_tracer(name: str):
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        # Fallback dummy tracer
        class DummySpan:
            def __enter__(self): return self
            def __exit__(self, exc_type, exc_val, exc_tb): pass
            def set_attribute(self, key, value): pass
            def add_event(self, name, attributes=None): pass
            def get_span_context(self): return None

        class DummyTracer:
            def start_as_current_span(self, name, context=None, kind=None):
                return DummySpan()
        
        return DummyTracer()

def trace_operation(op_name: str):
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            tracer = get_tracer(__name__)
            with tracer.start_as_current_span(op_name) as span:
                trace_id = kwargs.get('trace_id') or kwargs.get('tr_id') or str(uuid.uuid4())
                span.set_attribute("trace_id", trace_id)
                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception as e:
                    span.set_attribute("error", True)
                    span.add_event(f"Exception: {str(e)}")
                    raise e
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            tracer = get_tracer(__name__)
            with tracer.start_as_current_span(op_name) as span:
                trace_id = kwargs.get('trace_id') or kwargs.get('tr_id') or str(uuid.uuid4())
                span.set_attribute("trace_id", trace_id)
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    span.set_attribute("error", True)
                    span.add_event(f"Exception: {str(e)}")
                    raise e
        import inspect
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator
