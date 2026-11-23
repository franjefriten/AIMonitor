# Diseño y guía de refactor del exporter OpenTelemetry

> Estado: diseño para guiar una implementación; este documento no implica que el refactor esté aplicado.

## 1. Objetivo

OpenTelemetry debe integrarse como un exporter administrado por AIMonitor, siguiendo el modelo de configuración y ciclo de vida de los demás exporters:

```text
configuración AIMonitor
    -> providers privados del SDK OpenTelemetry
    -> procesadores/readers y exporters OTLP
    -> endpoint OTLP configurado por el usuario
    -> Collector o backend compatible
```

AIMonitor envía telemetría al endpoint configurado. No necesita implementar una integración distinta para cada backend que acepte OTLP. El Collector es opcional; puede recibir los datos y reenviarlos, pero AIMonitor no controla esa distribución posterior.

El exporter no debe asumir que la aplicación ha creado un provider global, ni instalar o reemplazar providers globales mediante `trace.set_tracer_provider()`, `metrics.set_meter_provider()` o `logs.set_logger_provider()`. Debe crear y cerrar sus propios providers privados.

### Responsabilidades y terminología

- El `OpenTelemetryExporter` de AIMonitor adapta los eventos de AIMonitor a señales OTel, configura providers privados para las señales activas y administra su ciclo de vida.
- Los exporters OTLP de OpenTelemetry son componentes del SDK que codifican y transportan esas señales al endpoint configurado. AIMonitor no implementa el protocolo protobuf.
- El destino puede ser un Collector o un backend compatible con OTLP. El Collector es opcional; si se necesita distribuir datos a varios backends, esa distribución queda fuera de AIMonitor.
- Los spans del provider privado no se integran automáticamente en trazas creadas por la aplicación u otras librerías. El contrato de AIMonitor solo garantiza la relación entre la ejecución MCP y sus spans anidados.

## 2. Contrato acordado y alcance

| Señal AIMonitor | Representación OpenTelemetry prevista |
| --- | --- |
| `MCPEvent` | Span raíz de la ejecución de la tool. |
| `SpanEvent` | Span hijo/anidado dentro de la misma traza. |
| `MetricEvent` | Métrica OpenTelemetry, según `MetricType`. |
| `LogEvent` | Registro de log OpenTelemetry. |
| Señales internas (`SignalType._INNER`) | No exportar desde este exporter. |

Decisiones ya acordadas:

- AIMonitor administra el SDK privado y el transporte OTLP cuando el exporter está habilitado.
- El usuario configura el destino mediante la configuración de AIMonitor.
- Los exporters tienen contratos distintos: Kafka publica los eventos de AIMonitor en topics; Prometheus expone agregados numéricos mediante scrape; OpenTelemetry convierte las señales habilitadas al modelo OTel y las envía por OTLP.
- La traza incluye el span raíz de la ejecución y sus `SpanEvent` anidados.
- `MCPEvent` y sus `SpanEvent` deben compartir una clave de correlación AIMonitor. El SDK genera los IDs OTel; el exporter conserva un mapping entre IDs internos de span y contextos OTel.
- `args` y `result` no se exportan por defecto; pueden contener datos sensibles.
- `MetricEvent`: `Counter.add`, `Histogram.record` y Gauge síncrono `set`. El SDK conserva la última observación del Gauge por conjunto de atributos; no hace falta una caché de valores Gauge propia.
- OpenTelemetry Python añadió el Gauge síncrono en `opentelemetry-api`/`opentelemetry-sdk` **v1.23.0**. El mínimo actual de AIMonitor, `>=1.29.0`, ya lo incluye.
- `MetricEvent.name` se usa como nombre del instrumento; `labels`, `environment` y `version` se usan como atributos. `metadata` se omite. Se añade `unit` opcional al modelo común, con default vacío.
- `LogEvent.message` es el body; `level` se convierte a severidad OTel estándar; `source`, `environment` y `version` son atributos. `metadata` se omite por defecto.
- `enabled` tiene toggles independientes `traces`, `metrics` y `logs`, todos `false` por defecto. Habilitar el exporter no activa señales implícitamente. Si el exporter está habilitado pero no hay señales activas, AIMonitor emite un warning y permite el no-op.
- Primera versión: solo OTLP/HTTP protobuf; no se añade un selector de protocolo ni soporte gRPC en este alcance. El SDK codifica protobuf. El intervalo de exportación de métricas es configurable y su default será 60 000 ms.
- `healthcheck()` mide readiness local de los providers configurados; no afirma que el backend remoto haya recibido o almacenado datos.
- Kafka y Prometheus conservan sus propios contratos: Kafka publica sus eventos en topics y Prometheus expone agregados numéricos.

### Decisiones aún abiertas

1. Política para cardinalidad alta de labels/series. No se ha decidido añadir un límite propio ni expulsar series.
2. Descripciones de instrumentos y validación de nombres/unidades.
3. Como los `SpanEvent` pueden llegar antes que el `MCPEvent` raíz, falta decidir límites de tamaño/tiempo para eventos pendientes y el comportamiento ante padres ausentes o trazas incompletas.
4. La conectividad y fallos de exportación remotos deben quedar diferenciados del readiness local; falta concretar cómo exponer fallos de exportación del SDK en los health snapshots.
5. Política general de compatibilidad por versiones de dependencias opcionales: fijar los mínimos soportados de cada exporter y decidir qué combinaciones de versiones de Python y dependencias se validarán en CI.

### Compatibilidad de dependencias opcionales

La compatibilidad tiene dos dimensiones distintas: versiones de Python y versiones de las bibliotecas opcionales que implementan cada integración. Que los tests pasen en varias versiones de Python con las dependencias más recientes no demuestra que funcionen con el mínimo declarado de cada paquete.

Actualmente, [`pyproject.toml`](../pyproject.toml) declara límites inferiores, sin máximos, por extra: OpenTelemetry API/SDK y OTLP HTTP desde `1.29.0`, `prometheus-client` desde `0.26.0`, `confluent-kafka` desde `2.15.0` y `aiosqlite` desde `0.22.1`. Son dependencias independientes: no todas son SDKs, pero cada exporter debe tener un rango de compatibilidad explícito.

La CI actual instala la resolución más reciente permitida por esos límites; la matriz de versiones de Python no prueba las versiones mínimas de las dependencias. Para cada exporter conviene validar al menos:

- La combinación de dependencias en los mínimos soportados.
- La combinación más reciente compatible, para detectar cambios de upstream.
- Las versiones de Python en las que esas combinaciones sean instalables, evitando asumir que hace falta ejecutar el producto cartesiano completo de todas las matrices.

Para OpenTelemetry, API, SDK y exporter OTLP forman una familia versionada: la prueba del mínimo debe instalar versiones compatibles entre sí. El Gauge síncrono existe desde `1.23.0`, pero AIMonitor declara `>=1.29.0`; el soporte declarado y probado por AIMonitor es el que determina el compromiso de compatibilidad, no la primera versión en que apareció la API.

Queda por decidir si se mantienen los mínimos actuales o se elevan, y qué estrategia de CI (por ejemplo, jobs de mínimos y latest por extra) ofrece cobertura suficiente sin multiplicar innecesariamente el coste de la matriz.

## 3. Estado actual del repositorio

La implementación actual de [`OpenTelemetryExporter`](../src/aimonitor/exporters/opentelemetry.py):

- Solo trabaja con `MCPEvent`.
- Obtiene un tracer con `trace.get_tracer(self.service_name)`, por lo que depende del provider global.
- No crea `TracerProvider`, `MeterProvider` ni `LoggerProvider`.
- No configura procesadores/readers ni exporters OTLP.
- No tiene `endpoint` en la configuración de [`OpenTelemetryExporterSettings`](../src/aimonitor/configs/config.py).
- No procesa `MetricEvent` ni `LogEvent`.

La configuración existente ya incluye `service_name` y `span_prefix`, y [`bootstrap.py`](../src/aimonitor/bootstrap.py) los pasa al exporter. En el diseño objetivo, `service_name` será el atributo de recurso `service.name`; `span_prefix` seguirá controlando los nombres de los spans.

El extra `opentelemetry` de [`pyproject.toml`](../pyproject.toml) contiene hoy `opentelemetry-api` y `opentelemetry-sdk`, pero no el paquete de exporters OTLP.

El Gauge síncrono está soportado desde v1.23.0. El código de la etiqueta v1.29.0 —el mínimo actual declarado por AIMonitor— contiene tanto `Meter.create_gauge()` como el SDK Gauge con `set()`. El Gauge no obliga a mantener una caché de valores en AIMonitor; sí hay que cachear el handle del instrumento, como se hace con otros instrumentos.

## 4. Configuración AIMonitor propuesta

Forma ilustrativa; los nombres/defaults finales deben seguir las convenciones del modelo de configuración:

```yaml
exporters:
  otel:
    enabled: true
    endpoint: "http://otel-collector:4318"
    service_name: "my-mcp-agent"
    span_prefix: "mcp.tool"
    signals:
      traces: false
      metrics: false
      logs: false
    metrics_export_interval_ms: 60000
```

- Los flags de señales en el ejemplo representan los defaults acordados: todos desactivados. Si se dejan así con `enabled: true`, AIMonitor avisa y el exporter no-op; el usuario activa explícitamente cada señal que quiera enviar.
- `endpoint` es la dirección base del receptor OTLP, no la URL de su interfaz web. Con OTLP/HTTP, el exporter construye las rutas por señal, por ejemplo `/v1/traces`, `/v1/metrics` y `/v1/logs`.
- El mismo endpoint puede recibir las tres señales, pero el SDK usa un provider y un procesador/reader para cada tipo.
- `signals` permite habilitar señales independientemente. No se expone una opción `protocol` mientras el único protocolo soportado sea HTTP/protobuf.
- Cabeceras de autenticación y secretos no deben guardarse en YAML sin protección; pueden añadirse después mediante configuración de entorno/secretos.

## 5. Snippets para refactorizar el exporter

Los siguientes snippets muestran las piezas y sus responsabilidades; no son una implementación completa. Las importaciones OTLP dependen del protocolo elegido.

### 5.1 Dependencias opcionales

El extra de OpenTelemetry necesita el SDK y un exporter OTLP. Para HTTP/protobuf, la documentación oficial usa:

```toml
[project.optional-dependencies]
opentelemetry = [
    "opentelemetry-api>=1.29.0",
    "opentelemetry-sdk>=1.29.0",
    "opentelemetry-exporter-otlp-proto-http>=1.29.0",
]
```

Mantener estas dependencias opcionales conserva ligero el paquete base.
El límite `>=1.29.0` ya incluye el Gauge síncrono, disponible desde v1.23.0. Usar la API pública `meter.create_gauge()`; no importar la clase de implementación interna `_Gauge`.

### 5.2 Crear providers privados en `connect()`

No usar `trace.get_tracer()` global ni registrar los providers privados como globales. Guardar los handles para que `close()` pueda hacer flush y apagarlos.

```python
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

resource = Resource.create({SERVICE_NAME: self.service_name})
traces_endpoint = f"{self.endpoint.rstrip('/')}/v1/traces"

self._tracer_provider = TracerProvider(resource=resource)
self._tracer_provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint=traces_endpoint))
)
self.tracer = self._tracer_provider.get_tracer("aimonitor")
```

Crear únicamente los providers correspondientes a las señales habilitadas. `connect()` debe ser idempotente y fallar explícitamente si falta una dependencia requerida o la configuración es inválida. El provider privado no debe registrarse como provider global ni reemplazar el de la aplicación.

### 5.3 Enrutar los tipos de señal

`export_batch()` puede hacer dispatch por modelo concreto, sin tratar cualquier señal como si tuviera los campos de `MCPEvent`:

```python
for event in event_batch:
    if isinstance(event, MCPEvent):
        self._export_tool_span(event)
    elif isinstance(event, SpanEvent):
        self._export_nested_span(event)
    elif isinstance(event, MetricEvent):
        self._record_metric(event)
    elif isinstance(event, LogEvent):
        self._record_log(event)
    elif event.event_type == SignalType._INNER:
        continue
```

No serializar `args` ni `result` como atributos por defecto. Aplicar una política explícita antes de añadir otros campos del evento como atributos OTel.

### 5.4 Providers de métricas y logs

OpenTelemetry separa los providers por señal. Este patrón es ilustrativo; crear los providers solo para señales habilitadas.

```python
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

metrics_endpoint = f"{self.endpoint.rstrip('/')}/v1/metrics"
metric_reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(endpoint=metrics_endpoint),
    export_interval_millis=self.metrics_export_interval_ms,
)
self._meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[metric_reader],
)
self.meter = self._meter_provider.get_meter("aimonitor")
```

El Gauge síncrono de la API Python tiene `set(amount, attributes=...)`. Cada actualización es una medida no aditiva; el SDK usa agregación de último valor al recolectar. Por tanto, el mapping conserva la semántica de AIMonitor sin una tabla de últimos valores administrada por el exporter:

```python
attributes = {
    **event.labels,
    **({"environment": event.environment} if event.environment else {}),
    **({"version": event.version} if event.version else {}),
}
instrument = self._instrument_for(event)  # Cached by name, type, and unit.

if event.metric_type == MetricType.COUNTER:
    instrument.add(event.value, attributes=attributes)
elif event.metric_type == MetricType.HISTOGRAM:
    instrument.record(event.value, attributes=attributes)
elif event.metric_type == MetricType.GAUGE:
    instrument.set(event.value, attributes=attributes)
```

Crear y cachear el **instrumento** por nombre, tipo y unidad; no cachear el valor Gauge. Repetir `set()` con los mismos atributos actualiza el último valor de esa serie en el SDK. El `PeriodicExportingMetricReader` recolecta y envía métricas al intervalo configurado; no se hace una petición HTTP por cada `MetricEvent`. `ObservableGauge` es otra opción para valores que el SDK debe consultar mediante callback, no la correspondencia necesaria para estos eventos que ya traen el valor.

```python
from opentelemetry._logs import SeverityNumber
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

logs_endpoint = f"{self.endpoint.rstrip('/')}/v1/logs"
self._logger_provider = LoggerProvider(resource=resource)
self._logger_provider.add_log_record_processor(
    BatchLogRecordProcessor(OTLPLogExporter(endpoint=logs_endpoint))
)
self.otel_logger = self._logger_provider.get_logger("aimonitor")

# Ejemplo dentro de _record_log(), tras acordar la conversión de severidad:
self.otel_logger.emit(
    severity_number=SeverityNumber.INFO,
    severity_text=event.level.value,
    body=event.message,
    attributes={"source": event.source},
)
```

Mapear los niveles `CRITICAL→FATAL`, `ERROR→ERROR`, `WARNING→WARN`, `INFO→INFO` y `DEBUG→DEBUG`. No incluir labels de alta cardinalidad sin una decisión explícita.

### 5.5 IDs y relación padre/hijo

Los IDs actuales generados por `Trace` incluyen nombres de operación y no pueden pasarse directamente como IDs de OpenTelemetry. No es necesario convertirlos en IDs OTel: se pueden conservar como claves internas de correlación y dejar que el SDK genere IDs OTel válidos.

```python
# Compartir este valor entre el MCPEvent raíz y sus SpanEvent.
trace_key = trace.trace_id
```

El contrato de eventos debe añadir `trace_id` a `MCPEvent`; `SpanEvent` ya lo tiene. Los `SpanEvent` de nivel superior (`parent_id is None`) cuelgan del span raíz `MCPEvent`. Los spans más profundos cuelgan del `SpanEvent` indicado por `parent_id`. No usar `metadata` como sustituto de campos de correlación tipados.

```python
# El SDK crea el ID OTel del span raíz.
root_span = self.tracer.start_span(root_name, start_time=root_start_ns)
root_otel_context = root_span.get_span_context()
root_span.end(end_time=root_end_ns)

# Para cada SpanEvent hijo, usar el contexto OTel del padre ya creado.
parent_otel_context = (
    root_otel_context
    if event.parent_id is None
    else otel_context_by_internal_span_id[event.parent_id]
)
parent_context = set_span_in_context(NonRecordingSpan(parent_otel_context))
span = self.tracer.start_span(name, context=parent_context, start_time=start_ns)
otel_context_by_internal_span_id[event.span_id] = span.get_span_context()
try:
    span.set_attribute("mcp.status", event.status.value)
finally:
    span.end(end_time=end_ns)
```

El snippet presupone que los eventos de una traza ya están agrupados y ordenados por dependencia. En el flujo actual los `SpanEvent` se despachan al cerrar cada context manager y el `MCPEvent` llega al terminar la tool; por eso el exporter probablemente tendrá que mantener eventos pendientes por `trace_id` hasta recibir la raíz, y después procesar la raíz antes que los hijos. Validar padres ausentes y evitar dejar trazas incompletas en memoria indefinidamente.

### 5.6 Cerrar correctamente el pipeline

Los procesadores por lotes pueden tener datos pendientes en workers del SDK. `close()` debe hacer flush y shutdown de cada provider creado, ejecutando las operaciones síncronas fuera del event loop:

```python
for provider in self._providers:
    await asyncio.to_thread(provider.force_flush)
    await asyncio.to_thread(provider.shutdown)
```

Mantener separados el resultado de `recover()` y el healthcheck posterior: recuperar o reconstruir un provider no demuestra que el backend esté recibiendo datos.

## 6. Etapas sugeridas

1. Añadir endpoint y configuración de señales al modelo YAML/JSON y probar su propagación por `bootstrap`.
2. Añadir el OTLP exporter como dependencia opcional.
3. Implementar providers privados y su lifecycle idempotente.
4. Extender el contrato de eventos para compartir la clave de correlación raíz/hijo y conservar la duración.
5. Implementar y probar el flujo de trazas con un exporter OTel en memoria, sin backend externo.
6. Implementar los mappings acordados de métricas y logs y probarlos con readers/exporters en memoria.
7. Añadir una prueba opcional con un Collector/backend OTLP real para comprobar transporte, sin hacerla requisito para la suite unitaria.

## 7. Referencias oficiales

- [OpenTelemetry Python: exporters](https://opentelemetry.io/docs/languages/python/exporters/) — configuración de OTLP, traces, metrics, Prometheus y Collector.
- [OpenTelemetry Python: instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/) — generación de telemetría desde Python.
- [OTLP exporter configuration](https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/) — endpoints, protocolos y variables de configuración.
- [OTLP specification](https://opentelemetry.io/docs/specs/otlp/) — protocolo de transporte.
- [Trace API specification](https://opentelemetry.io/docs/specs/otel/trace/api/) — spans, contexto e IDs.
- [Metrics API specification](https://opentelemetry.io/docs/specs/otel/metrics/api/) — instrumentos y observaciones.
- [OpenTelemetry Python metrics API](https://opentelemetry-python.readthedocs.io/en/stable/api/metrics.html) — `Gauge.set`, `Counter.add` y `Histogram.record`.
- [Metrics SDK specification](https://opentelemetry.io/docs/specs/otel/metrics/sdk/) — agregaciones SDK, incluida last-value aggregation.
- [OpenTelemetry Python v1.23.0 release](https://github.com/open-telemetry/opentelemetry-python/releases/tag/v1.23.0) — incluye “Add Synchronous Gauge instrument”.
- [OpenTelemetry Python v1.29.0 SDK Gauge implementation](https://github.com/open-telemetry/opentelemetry-python/blob/v1.29.0/opentelemetry-sdk/src/opentelemetry/sdk/metrics/_internal/instrument.py) — `Gauge.set()` consume una medida.
- [OpenTelemetry Python v1.29.0 Meter implementation](https://github.com/open-telemetry/opentelemetry-python/blob/v1.29.0/opentelemetry-sdk/src/opentelemetry/sdk/metrics/_internal/__init__.py) — `Meter.create_gauge()` crea el instrumento del SDK.
- [Logs API specification](https://opentelemetry.io/docs/specs/otel/logs/api/) — log records y severidad.
- [Logs SDK specification](https://opentelemetry.io/docs/specs/otel/logs/sdk/) — providers y processors de logs.
- [OpenTelemetry Collector](https://opentelemetry.io/docs/collector/) — recibir, procesar y reenviar señales.
