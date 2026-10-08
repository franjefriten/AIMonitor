# Diseño de healthchecks, estado y recuperación

## 1. Objetivo

Este documento propone una evolución de los healthchecks de AIMonitor. La intención no es convertir el SDK en un orquestador completo, sino conseguir cuatro capacidades claras:

1. Saber si el proceso está vivo.
2. Saber si los exporters están preparados para trabajar.
3. Conservar el último resultado de cada healthcheck, incluyendo timestamps y errores.
4. Intentar recuperar exporters con fallos transitorios sin ocultar fallos persistentes.

El diseño está pensado para que la implementación pueda hacerse por etapas y sirva también como ejercicio de aprendizaje sobre estado, ciclo de vida, concurrencia y tolerancia a fallos.

## 2. Estado actual

La API pública ya separa dos conceptos importantes:

- `get_liveness()`: debe ser barato y no contactar con dependencias externas.
- `get_readiness()`: informa sobre los exporters registrados y sus dependencias.

Actualmente `get_readiness()` obtiene el estado llamando a `status()` sobre los exporters en el momento de la consulta. Esto funciona para una primera versión, pero tiene varias limitaciones:

- Cada petición de readiness puede ejecutar trabajo adicional.
- No existe un historial del último healthcheck.
- No se distingue entre un exporter que nunca ha sido comprobado y uno que acaba de recuperarse.
- No se conservan contadores de fallos consecutivos.
- El estado depende de la implementación concreta de `status()` de cada exporter.

El worker de healthchecks está en `core/registry.py`, que también controla el registro, los workers de exportación, la cola y el cierre de exporters. Por tanto, el registry es el lugar que conoce todo el ciclo de vida.

## 3. ¿Debe existir otro singleton?

No se recomienda crear otro singleton para el estado.

El estado de health debe pertenecer al `ExporterRegistry`, porque el registry es el propietario de:

- Los exporters registrados.
- El worker que ejecuta los healthchecks.
- Las operaciones `register()` y `shutdown()`.
- La eventual recuperación de exporters.
- La relación entre una instancia concreta y su resultado de healthcheck.

Otro singleton introduciría estado global duplicado y una segunda fuente de verdad. También haría más difícil razonar sobre tests, reinicios y múltiples event loops.

La idea preferida es que el registry tenga un estado privado:

```python
self._health: dict[int, ExporterHealth] = {}
```

La clave debe identificar la instancia del exporter, no solamente el nombre de su clase. Puede haber dos exporters del mismo tipo con destinos diferentes.

La API pública no debería devolver directamente ese diccionario mutable. Es mejor que el registry genere una copia serializable mediante un método como:

```python
snapshot = registry.health_snapshot()
```

El snapshot es una vista del estado, no el estado interno que otros componentes puedan modificar accidentalmente.

## 4. Modelo de estado recomendado

El estado puede encapsularse en un `dataclass` en lugar de usar diccionarios sin estructura:

```python
@dataclass
class ExporterHealth:
    status: str = "starting"
    last_check_started_at: datetime | None = None
    last_check_finished_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    message: str = ""
```

El dataclass aporta nombres explícitos, valores por defecto y un lugar único donde ampliar el modelo. El JSON se puede construir posteriormente con una función de serialización.

### Estados

| Estado | Significado |
| --- | --- |
| `starting` | El exporter está registrado, pero todavía no tiene un healthcheck concluido. |
| `healthy` | El último healthcheck terminó correctamente. |
| `recovering` | Existe un fallo y se está intentando reconectar o reconstruir el exporter. |
| `down` | El exporter debería estar activo, pero el fallo persiste. |
| `stopped` | El exporter se ha detenido explícitamente como parte del cierre o de una orden administrativa. |
| `unused` | El exporter está deshabilitado, no tiene destino configurado o no participa en la ejecución. |

`starting` es útil porque evita clasificar como `healthy` un exporter cuyo estado todavía no conocemos.

`stopped` y `down` no significan lo mismo. `stopped` es una decisión deliberada del ciclo de vida; `down` es un fallo inesperado o persistente.

`unused` debería reservarse para exporters que realmente no forman parte de la ejecución activa. No debe usarse como sinónimo de `down` ni de "todavía no comprobado".

## 5. Timestamps y snapshot

El estado debería distinguir al menos estos momentos:

- `checked_at`: cuándo se construye el snapshot actual.
- `last_check_started_at`: cuándo comenzó el último healthcheck.
- `last_check_finished_at`: cuándo terminó.
- `last_success_at`: última comprobación correcta.
- `last_failure_at`: último fallo.

Todos deberían usar timestamps conscientes de zona horaria, preferiblemente UTC:

```python
from datetime import UTC, datetime

now = datetime.now(UTC)
```

Un snapshot podría tener esta forma:

```json
{
  "status": "degraded",
  "checked_at": "2026-10-08T19:30:00.120000+00:00",
  "summary": {
    "total_exporters": 2,
    "healthy_count": 1,
    "recovering_count": 1,
    "down_count": 0
  },
  "exporters": [
    {
      "name": "PrometheusExporter",
      "status": "healthy",
      "last_check_finished_at": "2026-10-08T19:29:59.900000+00:00",
      "last_success_at": "2026-10-08T19:29:59.900000+00:00",
      "last_failure_at": null,
      "consecutive_failures": 0,
      "message": "Exporter is operational."
    }
  ]
}
```

El `status()` de cada exporter puede seguir existiendo para detalles propios, pero no debería ser la fuente del historial del registry. El worker debe registrar el resultado después de cada healthcheck.

## 6. Separar `status()` de `healthcheck()`

Conviene mantener responsabilidades diferentes:

- `healthcheck()`: realiza una comprobación activa y puede contactar con la dependencia.
- `status()`: devuelve información del exporter.
- `health_snapshot()`: devuelve el estado histórico mantenido por el registry.

En particular, `get_readiness()` debería leer el snapshot cacheado en lugar de lanzar probes nuevos. Esto hace que la ruta sea predecible y barata.

Una consecuencia operativa es que readiness puede mostrar un resultado ligeramente antiguo. Esa antigüedad es controlable exponiendo `last_check_finished_at` y, si se desea, un `stale: true` cuando el resultado supere una edad máxima.

## 7. Timeout e intervalo

El intervalo indica cada cuánto se ejecuta un healthcheck. El timeout indica cuánto puede durar uno.

No deben compartir necesariamente el mismo valor:

```text
healthcheck_interval = 60 segundos
healthcheck_timeout = 5 segundos
```

Usar el intervalo completo como timeout puede bloquear el ciclo durante demasiado tiempo y retrasar la comprobación de otros exporters. La configuración debería incorporar un campo separado, por ejemplo:

```python
healthcheck_timeout: float = 5.0
```

También hay que decidir si el loop será secuencial o concurrente. El enfoque secuencial es más sencillo y evita una avalancha de tareas, pero un exporter lento puede retrasar a los demás. Una evolución posterior podría usar una tarea por exporter con límites y cancelación controlada.

Para el primer acercamiento, se puede mantener el loop secuencial y corregir el timeout. Es un cambio pequeño y fácil de probar.

## 8. Recuperación automática

La recuperación automática es útil, pero no debe confundirse con los retries de exportación.

### Retries de operación

La política existente de retries está pensada para una operación concreta:

```text
fallo al enviar un batch
    -> reintentar el envío
```

Su objetivo es tolerar un fallo puntual de red o de la dependencia.

### Recuperación del exporter

La recuperación trata el ciclo de vida de una instancia:

```text
healthcheck falla
    -> registrar el fallo
    -> marcar recovering
    -> cerrar o reconectar
    -> comprobar de nuevo
    -> healthy o down
```

Por eso no conviene reutilizar directamente el decorador de retries de `export_batch()`. Son políticas distintas, con límites, logs y consecuencias diferentes.

El contrato base podría incorporar una operación opcional:

```python
async def recover(self) -> bool:
    await self.close()
    await self.connect()
    return True
```

Pero no todos los exporters tienen una conexión que pueda reconstruirse. Una implementación por defecto podría devolver `False`, o la recuperación podría comprobar explícitamente si el exporter ofrece el método.

### Política mínima recomendada

```python
recovery_enabled = True
recovery_max_attempts = 3
recovery_backoff_seconds = 5.0
```

Flujo sugerido:

1. El primer fallo actualiza el estado y los contadores.
2. El exporter pasa a `recovering` si la recuperación está habilitada.
3. Se ejecuta `recover()` con backoff.
4. Después de recuperar, se ejecuta un healthcheck.
5. Si funciona, pasa a `healthy` y se reinician los fallos consecutivos.
6. Si se agotan los intentos, pasa a `down`.
7. El exporter no se elimina automáticamente del registry.

No se recomienda intentar recuperar indefinidamente. Un loop permanente de reconexión puede generar ruido, consumo de recursos y presión sobre un servicio externo caído.

La estrategia de reconstruir completamente un exporter requiere una factory o una función creadora, porque el registry no siempre conoce los argumentos necesarios para crear una instancia nueva. Por eso el primer paso debería ser `close()` más `connect()`; la recreación puede añadirse después mediante una política explícita.

## 9. Fallos durante la exportación

Actualmente el registry elimina exporters que fallan durante `_send_batch()`. Esto es una decisión importante que debe revisarse antes de añadir recovery.

Si un exporter se elimina inmediatamente:

- Ya no aparece en readiness.
- Se pierde su historial.
- No puede recuperarse automáticamente desde el registry.

Para soportar recuperación, sería preferible conservarlo en la colección, marcarlo como `down` o `recovering` y decidir si se omiten temporalmente sus envíos.

Otra posibilidad es mantener la eliminación como comportamiento opcional, pero entonces debe existir un registro separado de exporters configurados y una factory capaz de recrearlos. Sin una factory no hay forma general de reconstruir una instancia arbitraria.

## 10. Reset y ciclo de vida

No conviene meter el estado de exporters dentro de `AIMonitorSettings.reset()`. La configuración y el runtime son responsabilidades diferentes.

La separación recomendada es:

```python
async def shutdown(self) -> None:
    """Stop workers and close exporters."""
    ...

async def reset(self) -> None:
    """Reset runtime state for tests or reconfiguration."""
    await self.shutdown()
    self._health.clear()
```

`shutdown()` debe representar una parada real. Puede dejar los exporters en estado `stopped` mientras genera un snapshot final, si ese comportamiento resulta útil.

`reset()` se utiliza para tests o para una reconfiguración completa y elimina el historial. Es el método que debería usar el fixture de pytest:

```python
await registry.reset()
get_settings().reset()
internal_telemetry_manager.reset()
```

El manager de telemetría sigue teniendo su propio `reset()`, pero no debe ser el dueño del estado de health. La telemetría observa y emite datos; el registry controla el ciclo de vida.

## 11. Métricas de recursos

Las métricas de recursos son interesantes, pero no deberían bloquear la primera versión del healthcheck.

El registry controla mejor estas métricas:

```json
{
  "queue_size": 12,
  "queue_capacity": 1000,
  "active_workers": 5,
  "batches_processed": 240,
  "events_processed": 12000,
  "export_failures": 3,
  "last_flush_duration_ms": 18.4
}
```

Estas métricas ayudan a detectar saturación y lentitud sin depender de herramientas externas.

La CPU y la memoria del proceso pueden añadirse opcionalmente mediante `psutil`:

```json
{
  "process_cpu_percent": 2.4,
  "process_rss_bytes": 52428800
}
```

No recomendaría medir CPU por exporter o por thread al principio:

- El SDK usa principalmente `asyncio`.
- Un exporter puede usar threads internos que el registry no controla.
- La atribución de CPU por thread no siempre es portable ni representativa.
- Añade complejidad y una dependencia adicional.

Primero conviene medir cola, workers, duración de batches y errores. Si aparecen problemas de rendimiento reales, entonces se puede estudiar instrumentación más detallada.

## 12. Tests necesarios

La implementación debería crecer acompañada de tests pequeños y específicos.

### Estado inicial

- Un exporter registrado empieza en `starting`.
- `get_liveness()` no invoca healthchecks.
- Un registry sin exporters devuelve `empty`.

### Healthcheck correcto

- Un check correcto pasa a `healthy`.
- Se actualiza `last_check_finished_at`.
- Se actualiza `last_success_at`.
- `consecutive_failures` vuelve a cero.

### Healthcheck fallido

- Se actualiza `last_failure_at`.
- Se incrementa `consecutive_failures`.
- El mensaje del error queda disponible.
- El exporter no desaparece accidentalmente del snapshot.

### Timeout

- Un exporter que excede `healthcheck_timeout` se trata como fallido.
- El loop continúa con los demás exporters.
- El intervalo no se usa como timeout.

### Recuperación

- Un exporter que falla y después recupera vuelve a `healthy`.
- Se reinician los contadores de fallos consecutivos.
- Se respeta `recovery_max_attempts`.
- Después del límite queda en `down`.
- El backoff no crea varias recuperaciones simultáneas para el mismo exporter.

### Reset

- `registry.reset()` cancela workers.
- Cierra exporters.
- Vacía exporters, cola y snapshots.
- No conserva datos entre tests.
- La identidad del singleton se mantiene si el proyecto depende de ella.

## 13. Orden de implementación recomendado

Para mantener el cambio manejable, se propone este orden:

1. Añadir el modelo `ExporterHealth`.
2. Añadir `_health` al `ExporterRegistry`.
3. Actualizar el worker para guardar timestamps, estados y contadores.
4. Añadir `health_snapshot()` y hacer que readiness lo utilice.
5. Separar `healthcheck_timeout` de `healthcheck_interval`.
6. Añadir `registry.reset()` y conectarlo al fixture.
7. Escribir tests de estado, timeout y reset.
8. Añadir `recover()` opcional.
9. Añadir backoff, límite de intentos y tests de recuperación.
10. Añadir métricas de cola y workers.
11. Evaluar métricas opcionales de proceso con `psutil`.

Este orden permite validar primero la semántica del estado antes de introducir reconexiones automáticas.

## 14. Decisiones que conviene tomar explícitamente

Antes de cerrar la implementación, hay varias decisiones de producto y operación:

- ¿Readiness debe ser estricto y fallar si un solo exporter está `down`, o debe devolver `degraded` si todavía hay exporters sanos?
- ¿Un exporter `recovering` debe considerarse listo?
- ¿Un exporter `unused` cuenta en `total_exporters`?
- ¿Cuánto tiempo puede tener un snapshot antes de considerarse obsoleto?
- ¿Los fallos de exportación deben retirar exporters o conservarlos para recovery?
- ¿La recuperación se hace mediante reconexión o se permite recrear instancias?
- ¿Debe existir un método público para registrar y detener exporters individualmente?
- ¿Las métricas de proceso deben ser dependencia obligatoria u opcional?

No hay una respuesta universal. Lo importante es que cada decisión quede reflejada en tests y en la documentación operacional.

## 15. Resultado esperado

La arquitectura final debería quedar conceptualmente así:

```text
ExporterRegistry
    ├── exporters
    ├── workers
    ├── queue
    ├── health state por exporter
    ├── healthcheck loop
    ├── recovery policy
    └── health_snapshot()

telemetry.api
    ├── get_liveness()  -> comprobación local y barata
    └── get_readiness() -> snapshot cacheado del registry

InternalTelemetryManager
    └── observa y publica métricas/traces, pero no posee el estado
```

La idea central es mantener una única fuente de verdad para el ciclo de vida: el registry. La API de health debe ser una vista segura y serializable de ese estado, y la recuperación debe ser una política explícita, limitada y observable.
