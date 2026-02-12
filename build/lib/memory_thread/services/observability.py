"""
OpenTelemetry Integration for Memory Thread.

Provides distributed tracing, metrics, and structured logging
for enterprise-grade observability.

Usage:
    # Auto-instruments FastAPI on import
    from memory_thread.services.observability import init_telemetry
    
    init_telemetry(service_name="memory-thread")

View traces:
    - Jaeger: http://localhost:16686
    - Console: Set MT_OTEL_CONSOLE=true
"""
import os
from typing import Optional
from functools import wraps
import time

# Check if OpenTelemetry is available
try:
    from opentelemetry import trace, metrics
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False

from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

# Global tracer
_tracer: Optional["trace.Tracer"] = None
_meter: Optional["metrics.Meter"] = None
_initialized = False


def init_telemetry(
    service_name: str = "memory-thread",
    otlp_endpoint: Optional[str] = None,
    console_export: bool = False
) -> bool:
    """
    Initialize OpenTelemetry tracing and metrics.
    
    Args:
        service_name: Name of this service in traces
        otlp_endpoint: OTLP collector endpoint (e.g., "localhost:4317")
        console_export: If True, also print spans to console
    
    Returns:
        True if initialized successfully, False if OTel not available
    """
    global _tracer, _meter, _initialized
    
    if _initialized:
        return True
    
    if not OTEL_AVAILABLE:
        log.warning("OpenTelemetry not installed. Run: pip install memory-thread[observability]")
        return False
    
    # Check environment
    otlp_endpoint = otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    console_export = console_export or os.getenv("MT_OTEL_CONSOLE", "").lower() == "true"
    
    # Create resource
    resource = Resource.create({
        SERVICE_NAME: service_name,
        "service.version": "1.0.0",
        "deployment.environment": os.getenv("MT_ENV", "development"),
    })
    
    # Setup tracer
    provider = TracerProvider(resource=resource)
    
    # Add exporters
    if otlp_endpoint:
        otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        log.info(f"OTel OTLP exporter configured: {otlp_endpoint}")
    
    if console_export:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        log.info("OTel console exporter enabled")
    
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(__name__)
    
    # Setup metrics
    meter_provider = MeterProvider(resource=resource)
    metrics.set_meter_provider(meter_provider)
    _meter = metrics.get_meter(__name__)
    
    _initialized = True
    log.info(f"OpenTelemetry initialized for '{service_name}'")
    return True


def get_tracer() -> Optional["trace.Tracer"]:
    """Get the global tracer."""
    return _tracer


def get_meter() -> Optional["metrics.Meter"]:
    """Get the global meter."""
    return _meter


def instrument_fastapi(app):
    """
    Instrument a FastAPI app with automatic tracing.
    
    Args:
        app: FastAPI application instance
    """
    if not OTEL_AVAILABLE:
        log.warning("Cannot instrument FastAPI: OpenTelemetry not available")
        return
    
    FastAPIInstrumentor.instrument_app(app)
    log.info("FastAPI instrumented with OpenTelemetry")


def traced(span_name: Optional[str] = None):
    """
    Decorator to trace a function.
    
    Usage:
        @traced("sdk.remember")
        def remember(content: str):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            tracer = get_tracer()
            if tracer is None:
                return func(*args, **kwargs)
            
            name = span_name or f"{func.__module__}.{func.__name__}"
            with tracer.start_as_current_span(name) as span:
                # Add function arguments as attributes
                span.set_attribute("function.name", func.__name__)
                
                try:
                    result = func(*args, **kwargs)
                    span.set_attribute("function.success", True)
                    return result
                except Exception as e:
                    span.set_attribute("function.success", False)
                    span.set_attribute("error.message", str(e))
                    span.record_exception(e)
                    raise
        
        return wrapper
    return decorator


def timed(metric_name: str):
    """
    Decorator to record function execution time as a metric.
    
    Usage:
        @timed("sdk.remember.duration")
        def remember(content: str):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            meter = get_meter()
            start = time.time()
            
            try:
                return func(*args, **kwargs)
            finally:
                duration = time.time() - start
                if meter:
                    histogram = meter.create_histogram(
                        metric_name,
                        unit="seconds",
                        description=f"Duration of {func.__name__}"
                    )
                    histogram.record(duration)
        
        return wrapper
    return decorator


# Convenience metrics
class MTMetrics:
    """Pre-defined metrics for Memory Thread."""
    
    def __init__(self):
        self._meter = get_meter()
        self._counters = {}
        self._histograms = {}
    
    def increment(self, name: str, value: int = 1, attributes: dict = None):
        """Increment a counter."""
        if not self._meter:
            return
        
        if name not in self._counters:
            self._counters[name] = self._meter.create_counter(
                name, description=f"Count of {name}"
            )
        self._counters[name].add(value, attributes or {})
    
    def record_duration(self, name: str, duration: float, attributes: dict = None):
        """Record a duration."""
        if not self._meter:
            return
        
        if name not in self._histograms:
            self._histograms[name] = self._meter.create_histogram(
                name, unit="seconds", description=f"Duration of {name}"
            )
        self._histograms[name].record(duration, attributes or {})


# Global metrics instance
mt_metrics = MTMetrics()
