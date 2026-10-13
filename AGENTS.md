# Reglas para LLM

Estas reglas aplican al trabajo de asistentes de IA en este repositorio.

## Principios de colaboración

- El código pertenece al desarrollador. El asistente debe ayudarle a entender, diseñar y mejorar el sistema, no sustituir su trabajo.
- Antes de editar, leer el código actual y formular una hipótesis concreta sobre el bug o el cambio necesario.
- Aplicar parches pequeños y localizados sobre la implementación existente.
- No reescribir una función o un subsistema desde cero si un parche incremental resuelve el problema.
- Preservar las decisiones de diseño, nombres públicos, contratos y estructura existentes salvo que el cambio sea imprescindible.
- Si la solución requiere una modificación estructural o afecta a varias capas, explicarlo antes de aplicarla y dividirla en pasos revisables.
- No corregir bugs no relacionados sin notificarlos primero.
- Si una implementación del usuario es incompleta pero válida como primer acercamiento, mejorarla progresivamente en lugar de reemplazarla.
- No borrar comentarios aclarativos del desarrollador; conservarlos al aplicar parches y reponerlos si un cambio los elimina accidentalmente.

## Cambios y validación

- Antes de editar, revisar también los cambios recientes del usuario y no sobrescribirlos.
- Después de cada parche sustancial, ejecutar primero el test o la comprobación más cercana al código modificado.
- Mantener los tests alineados con el contrato actual, pero no ocultar incompatibilidades cambiando expectativas sin explicarlo.
- Informar de los riesgos restantes, los cambios grandes y cualquier validación que no haya podido ejecutarse.
- No crear commits ni revertir cambios del usuario salvo petición explícita.

## Healthchecks y recovery

- Mantener separadas las responsabilidades de actualizar snapshots, detectar/publicar transiciones y escribir logs.
- La detección de una transición debe comparar el snapshot anterior con el nuevo antes de sobrescribirlo.
- El recovery debe evolucionar mediante parches sobre el flujo existente; no debe reescribirse completo sin avisar y acordar el alcance.
- Un recovery exitoso debe distinguir entre que `recover()` termine bien y que un healthcheck posterior confirme el estado saludable.
