# Python Package Migration Plan

## Objective

Migrate AIMonitor from top-level packages to a `src` layout with one public namespace:

```python
import aimonitor

from aimonitor.core.decorators import monitor_tool
from aimonitor.exporters.file import FileExporter
from aimonitor.bootstrap import initialize_monitor
```

The distribution remains:

```bash
pip install ai-monitor-sdk
```

The migration must prevent `core`, `configs`, `exporters`, `telemetry`, `utils`, and `bootstrap.py` from being installed as top-level packages.

## Current state

- The reference repository is `C:\Users\Usuario\Desktop\AIMonitor`.
- Migration work must start from `develop`, not directly from `main` or from an old feature branch.
- Integrate `roadmap-P0` into `develop` before promoting work to `main`.
- The published distribution is `ai-monitor-sdk`.
- The current published version is `0.0.1`.
- Runtime modules still use top-level directories:
  - `core/`
  - `configs/`
  - `exporters/`
  - `telemetry/`
  - `utils/`
  - `bootstrap.py`
- The existing `aimonitor/` facade is provisional and is not the final package layout.

## Target structure

```text
src/
└── aimonitor/
    ├── __init__.py
    ├── bootstrap.py
    ├── core/
    ├── configs/
    ├── exporters/
    ├── telemetry/
    └── utils/
```

A wheel should install only `aimonitor/` under `site-packages`. It must not install top-level `core`, `configs`, `exporters`, `telemetry`, `utils`, or `bootstrap.py` modules.

## Branch strategy

Recommended flow:

```text
roadmap-P0 -> develop -> main
```

### Integrate Phase 0

If Phase 0 work already exists on `roadmap-P0`, open:

```text
roadmap-P0 -> develop
```

Before opening the pull request:

```powershell
git fetch origin --prune
git switch roadmap-P0
git status --short --branch
git log --oneline develop..roadmap-P0
```

Run the pull request checks before merging.

### Migration branch

After `roadmap-P0` is merged into `develop`, create a dedicated branch:

```powershell
git switch develop
git pull --ff-only origin develop
git switch -c package-layout-migration
```

Open:

```text
package-layout-migration -> develop
```

Alternatively, if the migration and Phase 0 are a single reviewable change, they may remain on `roadmap-P0` and use `roadmap-P0 -> develop`.

Do not overwrite staged or unrelated user changes.

## Integration order

The migration must reach `develop` before `main`:

1. Commit the new structure and packaging configuration.
2. Commit internal import, test, and documentation updates.
3. Commit pipeline and installed-wheel validation.
4. Run the complete CI suite against `develop`.
5. Merge only after checks pass.
6. Do not publish a new version until migration is validated.

When `develop` is stable:

1. Run unit, integration, and wheel validation again.
2. Open `develop -> main`.
3. Wait for publication checks.
4. Merge and create the release from the integrated commit.

Publishing must originate from the integrated `main` state.

## Existing branch policy

The layout change breaks imports that use top-level `core`, `configs`, `exporters`, `telemetry`, or `utils`.

| Branch type | Action |
| --- | --- |
| Already merged into `develop` or `main` | Delete after confirming it is no longer needed. |
| Open but obsolete pull request | Close and document the reason. |
| Useful but unmerged work | Port functional commits onto a new branch based on `develop`. |
| Active development | Inform the author and plan a rebase or port. |
| Release or hotfix | Keep until migration and publication are complete. |

Inspect branches with:

```powershell
git branch --all --merged develop
git log --oneline develop..branch-name
git log --oneline --decorate --graph --all
```

Do not use `git branch -D` or delete remote branches until unique work is checked.

## Implementation phases

### Phase 1: Prepare the package

Create `src/aimonitor/` and move runtime modules:

```powershell
New-Item -ItemType Directory -Force src\aimonitor | Out-Null
git mv bootstrap.py src\aimonitor\bootstrap.py
git mv core src\aimonitor\core
git mv configs src\aimonitor\configs
git mv exporters src\aimonitor\exporters
git mv telemetry src\aimonitor\telemetry
git mv utils src\aimonitor\utils
```

Move or adapt the provisional facade to `src/aimonitor/__init__.py`. Remove `sys.modules`-based compatibility logic.

The public `__init__.py` should expose a stable version and API. It should not eagerly import every exporter.

### Phase 2: Configure setuptools

In `pyproject.toml`, replace explicit package lists with source-layout discovery:

```toml
[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]
```

Remove entries such as:

```toml
packages = ["aimonitor", "core", "exporters", "utils", "configs", "telemetry"]
py-modules = ["bootstrap"]
```

The final configuration must discover only packages below `src/aimonitor`.

### Phase 3: Migrate imports

Before:

```python
from core.event import MCPEvent
from exporters.base import BaseExporter
from configs.config import get_settings
from telemetry.api import telemetry_producer
from utils.logger import logger
from bootstrap import initialize_monitor
```

After:

```python
from aimonitor.core.event import MCPEvent
from aimonitor.exporters.base import BaseExporter
from aimonitor.configs.config import get_settings
from aimonitor.telemetry.api import telemetry_producer
from aimonitor.utils.logger import logger
from aimonitor.bootstrap import initialize_monitor
```

Find old imports with:

```powershell
rg "^(from|import) (core|configs|exporters|telemetry|utils|bootstrap)" .
```

No top-level imports of those old packages should remain in code, tests, or examples.

### Phase 4: Migrate tests and documentation

Tests must use the public package API:

```python
import aimonitor

from aimonitor.core.decorators import monitor_tool
from aimonitor.core.registry import registry
from aimonitor.exporters.file import FileExporter
```

Update at minimum:

- `README.md`
- `docs/usage.md`
- `docs/installation.md`
- `docs/examples.md`
- `docs/configuration.md`
- `docs/healthchecks.md`
- `docs/architecture.md`
- `docs/CONTRIBUTING.md`

### Phase 5: Validate locally

Clean build artifacts:

```powershell
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force src\aimonitor.egg-info -ErrorAction SilentlyContinue
python -m build
python -m pip install --target .\tmp-wheel-install dist\ai_monitor_sdk-*.whl
```

Verify:

- `aimonitor` imports from the wheel.
- Top-level `core`, `configs`, `exporters`, `telemetry`, `utils`, and `bootstrap` do not exist.
- Public imports work in a process outside the repository checkout.
- Unit and integration tests do not depend on the source tree.

### Phase 6: Update CI and publication

CI must validate the installed wheel, not only the checkout:

```yaml
- run: python -m build
- run: python -m pip install dist/*.whl
- run: python -m pytest
```

Unit jobs must work without external services. Integration jobs may use Kafka and Prometheus.

Publication workflows must repeat the check before publishing. The build and publication job does not need to install optional exporter extras.

### Phase 7: Release

Do not overwrite `0.0.1`. After migration is validated in `develop` and `main`:

1. Confirm the installed namespace.
2. Run a smoke test outside the checkout.
3. Open the release pull request.
4. Publish `ai-monitor-sdk` from the merge commit.

## Acceptance criteria

- Every runtime import starts with `aimonitor`.
- No top-level compatibility packages remain in the wheel.
- The current public API is available after a normal pip install.
- Unit tests pass without external services.
- The wheel is tested outside the source checkout.
- CI reproduces the clean-checkout process.
- Documentation uses only `aimonitor.*` imports.
- Publication fails if namespace validation fails.

## Risks

- Old branches may still import top-level modules.
- Third-party code may depend on accidental top-level packages.
- Building the source tree can hide wheel discovery problems.
- Optional dependencies may change import behavior.
- Releasing from an unintegrated branch can publish an untested layout.

## Closing rule

The migration is not complete because checkout tests pass. Close it only when an installed wheel exposes `aimonitor` correctly and the publication pipeline validates that artifact automatically.
