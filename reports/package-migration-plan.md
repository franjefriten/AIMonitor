# Plan de migración del paquete Python

## Objetivo

Migrar AIMonitor desde una estructura de paquetes top-level a una estructura `src` con un único namespace público:

```python
import aimonitor

from aimonitor.core.decorators import monitor_tool
from aimonitor.exporters.file import FileExporter
from aimonitor.bootstrap import initialize_monitor
```

La distribución seguirá instalándose con:

```bash
pip install ai-monitor-sdk
```

El resultado debe evitar que `core`, `configs`, `exporters`, `telemetry` y `utils` se instalen directamente en `site-packages`.

## Estado actual

- Repositorio: `C:\Users\Usuario\Desktop\AIMonitor`.
- Rama de referencia de Phase 0: `roadmap-P0`.
- La migración debe partir de `develop`, no directamente de `main` ni de una rama de funcionalidad antigua.
- `roadmap-P0` debe integrarse en `develop` antes de promover el resultado a `main`.
- La distribución publicada se llama `ai-monitor-sdk`.
- La versión publicada actual es `0.0.1`.
- El código actual todavía vive en directorios top-level:
  - `core/`
  - `configs/`
  - `exporters/`
  - `telemetry/`
  - `utils/`
  - `bootstrap.py`
- Existe una fachada provisional en `aimonitor/`, pero no debe ser la solución definitiva.

## Estructura objetivo

```text
src/
└── aimonitor/
    ├── __init__.py
    ├── bootstrap.py
    ├── core/
    │   ├── __init__.py
    │   ├── decorators.py
    │   ├── event.py
    │   ├── observability.py
    │   ├── registry.py
    │   └── trace.py
    ├── configs/
    │   ├── __init__.py
    │   └── config.py
    ├── exporters/
    │   ├── __init__.py
    │   ├── base.py
    │   ├── console.py
    │   ├── file.py
    │   ├── http.py
    │   ├── kafka.py
    │   ├── opentelemetry.py
    │   ├── prometheus.py
    │   └── sqlite.py
    ├── telemetry/
    │   ├── __init__.py
    │   └── api.py
    └── utils/
        ├── __init__.py
        ├── context.py
        ├── logger.py
        └── security.py
```

El wheel debe instalar únicamente el namespace:

```text
site-packages/
└── aimonitor/
    ├── bootstrap.py
    ├── core/
    ├── configs/
    ├── exporters/
    ├── telemetry/
    └── utils/
```

No debe instalar estos elementos como paquetes de primer nivel:

```text
core/
configs/
exporters/
telemetry/
utils/
bootstrap.py
```

## Estrategia de ramas

La migración no debe hacerse directamente sobre `main` ni sobre `develop`.

Para integrar primero el trabajo actual, el flujo es:

```text
roadmap-P0
    |
    v
develop
    |
    v
main
```

### Integración del trabajo actual de Phase 0

Si los cambios de Phase 0 ya están en `roadmap-P0`, basta con abrir un Pull Request:

```text
roadmap-P0 -> develop
```

No hace falta crear otra rama para ese paso.

Antes de abrirlo:

```powershell
git fetch origin --prune
git switch roadmap-P0
git status --short --branch
git log --oneline develop..roadmap-P0
```

El PR debe incluir los cambios de Phase 0 y pasar sus checks antes de fusionarse.

### Rama para la migración del layout

La migración `src/aimonitor` es un trabajo posterior y no existe automáticamente por abrir el PR anterior. Una vez que `roadmap-P0` esté integrado en `develop`, hay dos opciones:

#### Opción recomendada: migración separada

Crear una rama nueva desde el `develop` actualizado:

```powershell
git switch develop
git pull --ff-only origin develop
git switch -c package-layout-migration
```

Esta rama contendrá exclusivamente la migración del empaquetado, imports, tests, documentación y pipelines.

Después se abrirá:

```text
package-layout-migration -> develop
```

#### Opción alternativa: migración dentro de `roadmap-P0`

Si se decide que Phase 0 y la migración forman un único cambio revisable, se puede hacer la migración directamente en `roadmap-P0` y abrir un único PR:

```text
roadmap-P0 -> develop
```

No es necesario crear `refactor/package-layout`. El nombre de una rama nueva solo sirve para aislar la migración, no tiene ninguna función técnica especial.

### Preparación antes de mover archivos

En cualquier opción:

```powershell
git status --short --branch
git log -5 --oneline
```

No se deben sobrescribir cambios staged ni cambios de usuario no relacionados.

### Integración en `develop`

La migración debe llegar primero a `develop` mediante un Pull Request:

1. Commit de la nueva estructura y configuración del empaquetado.
2. Commit de imports, tests y documentación.
3. Commit de pipelines y validación del artefacto.
4. Ejecutar CI completo contra `develop`.
5. Revisar el PR contra `develop`.
6. Fusionar únicamente cuando los checks sean verdes.

No publicar la nueva versión antes de validar la migración en `develop`.

### Integración en `main`

Cuando `develop` esté estable:

1. Ejecutar nuevamente unitarios, integración y validación del wheel.
2. Abrir un PR de `develop` hacia `main`.
3. Esperar los checks específicos de publicación.
4. Fusionar a `main`.
5. Crear la release desde el commit ya integrado.

La publicación a PyPI debe salir del estado integrado en `main`.

## Política para las ramas existentes

El cambio de layout rompe los imports de las ramas que todavía usan `core`, `configs`, `exporters`, `telemetry` o `utils` como paquetes top-level. Aun así, no conviene borrarlas todas inmediatamente.

| Tipo de rama                          | Acción                                                             |
| ------------------------------------- | ------------------------------------------------------------------- |
| Ya fusionada en`develop` o `main` | Eliminar después de confirmar que no se necesita                   |
| PR abierto pero obsoleto              | Cerrar, documentar el motivo y eliminar                             |
| Trabajo útil no fusionado            | Congelar y portar los commits a una rama nueva basada en`develop` |
| Desarrollo activo                     | Mantener y avisar al autor para planificar el rebase                |
| Release o hotfix                      | Mantener hasta completar la migración y publicar                   |

Para clasificar ramas:

```powershell
git branch --all --merged develop
git log --oneline develop..T1
git log --oneline develop..T9-kafka
git log --oneline --decorate --graph --all
```

No usar `git branch -D` ni borrar ramas remotas hasta comprobar que no contienen trabajo único.

Para portar una rama que siga siendo necesaria:

```powershell
git switch develop
git pull --ff-only origin develop
git switch -c port/<feature-name>-after-package-migration
```

Portar únicamente los commits funcionales y actualizar sus imports a `aimonitor.*`. No hacer un rebase masivo de todas las ramas antes de estabilizar `develop`.

## Fases de implementación

### Fase 1: Preparar el empaquetado

1. Crear `src/aimonitor/`.
2. Mover los módulos con `git mv`:

   ```powershell
   New-Item -ItemType Directory -Force src\aimonitor | Out-Null
   git mv bootstrap.py src\aimonitor\bootstrap.py
   git mv core src\aimonitor\core
   git mv configs src\aimonitor\configs
   git mv exporters src\aimonitor\exporters
   git mv telemetry src\aimonitor\telemetry
   git mv utils src\aimonitor\utils
   ```
3. Mover o adaptar el `__init__.py` provisional a `src/aimonitor/__init__.py`.
4. Eliminar la lógica basada en `sys.modules`.
5. Crear `src/aimonitor/telemetry/__init__.py` si no existe.

El `__init__.py` público debe limitarse a exponer la versión y una API estable. No debe importar todos los exporters automáticamente.

### Fase 2: Configurar setuptools

En `pyproject.toml`, reemplazar la lista explícita de paquetes por descubrimiento bajo `src`:

```toml
[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]
```

Eliminar:

```toml
packages = ["aimonitor", "core", "exporters", "utils", "configs", "telemetry"]
py-modules = ["bootstrap"]
```

La configuración final debe descubrir solo los paquetes bajo `src/aimonitor`.

### Fase 3: Migrar imports

Actualizar imports internos, tests, ejemplos y documentación.

Antes:

```python
from core.event import MCPEvent
from exporters.base import BaseExporter
from configs.config import get_settings
from telemetry.api import telemetry_producer
from utils.logger import logger
from bootstrap import initialize_monitor
```

Después:

```python
from aimonitor.core.event import MCPEvent
from aimonitor.exporters.base import BaseExporter
from aimonitor.configs.config import get_settings
from aimonitor.telemetry.api import telemetry_producer
from aimonitor.utils.logger import logger
from aimonitor.bootstrap import initialize_monitor
```

Localizar referencias antiguas con:

```powershell
rg "^(from|import) (core|configs|exporters|telemetry|utils|bootstrap)" .
```

No deben quedar imports de esos paquetes como top-level en código, tests ni ejemplos.

### Fase 4: Migrar tests y documentación

Los tests deben usar la API pública:

```python
import aimonitor

from aimonitor.core.decorators import monitor_tool
from aimonitor.core.registry import registry
from aimonitor.exporters.file import FileExporter
```

La documentación debe mantener:

```bash
pip install ai-monitor-sdk
```

y ejemplos como:

```python
import aimonitor

from aimonitor.core.decorators import monitor_tool
```

Actualizar como mínimo:

- `README.md`
- `docs/usage.md`
- `docs/installation.md`
- `docs/examples.md`
- `docs/configuration.md`
- `docs/healthchecks.md`
- `docs/architecture.md`
- `docs/CONTRIBUTING.md`

### Fase 5: Validación local

Eliminar artefactos de builds anteriores:

```powershell
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
```

Instalar el proyecto en editable:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[opentelemetry,sqlite,prometheus,kafka]"
```

Ejecutar unitarios:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit -q
```

Construir y comprobar el paquete:

```powershell
.\.venv\Scripts\python.exe -m build
.\.venv\Scripts\python.exe -m twine check dist\*
```

Comprobar el contenido del wheel:

```powershell
@'
import glob
import zipfile

wheel = glob.glob("dist/*.whl")[0]
with zipfile.ZipFile(wheel) as archive:
    names = archive.namelist()

assert any(name.startswith("aimonitor/") for name in names)
assert not any(name.startswith("core/") for name in names)
assert not any(name.startswith("configs/") for name in names)
assert not any(name.startswith("exporters/") for name in names)
assert not any(name.startswith("telemetry/") for name in names)
assert not any(name.startswith("utils/") for name in names)
assert "bootstrap.py" not in names
print("Wheel layout is valid")
'@ | .\.venv\Scripts\python.exe -
```

Probar el wheel fuera del checkout:

```powershell
$python = (Resolve-Path .\.venv\Scripts\python.exe).Path
New-Item -ItemType Directory -Force .tmp-package-check | Out-Null
Push-Location .tmp-package-check
& $python -c "import aimonitor; from aimonitor.core.decorators import monitor_tool; from aimonitor.bootstrap import initialize_monitor; print(aimonitor.__version__)"
Pop-Location
Remove-Item -Recurse -Force .tmp-package-check
```

### Fase 6: Ajustar CI y publicación

Los workflows deben validar el wheel instalado, no solo el código del checkout:

- `.github/workflows/python-tests.yml`
- `.github/workflows/publish-testpypi.yaml`
- `.github/workflows/publish.yaml`

Cada validación de artefacto debe:

1. Ejecutar `python -m build`.
2. Ejecutar `python -m twine check dist/*`.
3. Instalar el wheel generado.
4. Ejecutar el smoke test desde un directorio externo:

   ```python
   import aimonitor
   from aimonitor.core.decorators import monitor_tool
   from aimonitor.bootstrap import initialize_monitor
   ```
5. Comprobar que no se instalaron paquetes top-level.

Los jobs de unitarios seguirán funcionando sin servicios externos. Los jobs de integración continuarán usando Kafka y Prometheus.

### Fase 7: Nueva versión y publicación

No sobrescribir `0.0.1`. Cuando la migración esté integrada y validada primero en `develop` y después en `main`:

1. Cambiar la versión en `pyproject.toml` a la siguiente versión, por ejemplo `0.0.2`.
2. Actualizar `CHANGELOG.md`.
3. Crear la release.
4. Publicar primero en TestPyPI.
5. Verificar instalación:

   ```powershell
   pip install --index-url https://test.pypi.org/simple/ ai-monitor-sdk
   ```
6. Publicar en PyPI.
7. Verificar:

   ```powershell
   pip install ai-monitor-sdk
   python -c "import aimonitor; print(aimonitor.__version__)"
   ```

## Criterios de aceptación

- `pip install ai-monitor-sdk` instala el paquete correctamente.
- `import aimonitor` funciona desde un directorio fuera del repositorio.
- Funcionan imports como `aimonitor.core`, `aimonitor.configs`, `aimonitor.exporters` y `aimonitor.bootstrap`.
- El wheel no contiene paquetes top-level `core`, `configs`, `exporters`, `telemetry` ni `utils`.
- Los unitarios pasan sin librerías opcionales ni servicios externos.
- Las integraciones pasan con Kafka y Prometheus disponibles.
- Los workflows de PR, TestPyPI y PyPI validan el wheel instalado.
- La documentación no usa imports top-level antiguos.
- La migración llega primero a `develop` y después a `main` mediante Pull Requests.
- La nueva publicación utiliza una versión superior a `0.0.1`.

## Riesgos

- Un import antiguo puede hacer que los tests pasen desde el checkout, pero fallen desde el wheel.
- Ejecutar tests desde la raíz puede ocultar errores de empaquetado.
- Los artefactos `build/`, `dist/` y `*.egg-info` pueden contener resultados de builds anteriores.
- La migración puede entrar en conflicto con cambios recientes en `roadmap-P0`.
- Los módulos opcionales deben conservar sus guards de importación para que la API base siga siendo importable sin extras.

## Regla de cierre

La migración no se considera terminada porque los tests del checkout pasen. Solo se cierra cuando el wheel instalado desde fuera del repositorio expone correctamente el namespace `aimonitor` y la pipeline de publicación lo valida automáticamente.
