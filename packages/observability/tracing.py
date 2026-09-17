from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def configure_tracing(endpoint: str | None) -> TracerProvider:
    provider = TracerProvider(resource=Resource.create({"service.name": "mts-api"}))
    if endpoint:
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, timeout=2))
        )
    # Use a provider per application; tests and restarts do not replace global state.
    return provider


def tracer_for(provider: TracerProvider) -> trace.Tracer:
    return provider.get_tracer("mytradingsystem", "0.2.0")
