# Contributing to AIMonitor

Thank you for your interest in contributing to AIMonitor! 🙌

This guide will help you understand our development workflow and how to contribute effectively.

## Code of Conduct

Be respectful, inclusive, and professional. We follow the [Contributor Covenant](https://www.contributor-covenant.org/).

## Getting started

### 1. Fork and clone

```bash
git clone https://github.com/yourusername/AIMonitor.git
cd AIMonitor
```

### 2. Set up development environment

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install with dev dependencies
pip install -e ".[opentelemetry,sqlite,metrics,redis,kafka]"
pip install pytest pytest-asyncio
```

### 3. Create a feature branch

```bash
git checkout -b feature/my-feature
# or
git checkout -b fix/bug-description
```

## Development workflow

### Running tests

```bash
# Unit tests
pytest tests/unit -v

# All tests
pytest tests/ -v

# Specific test file
pytest tests/unit/test_decorators.py -v

# With coverage
pytest --cov=. tests/
```

### Code style

- Follow PEP 8 guidelines
- Use type hints where possible
- Keep functions focused and well-documented

Example:

```python
async def export(self, event: MCPEvent) -> None:
    """
    Export a single event.
    
    Args:
        event: The MCPEvent to export
    """
    await self.export_batch([event])
```

### Adding features

1. **Create tests first** (TDD approach recommended)
2. **Implement the feature**
3. **Update documentation** if needed
4. **Run tests** and verify no regressions

### Adding exporters

To add a new exporter:

1. Inherit from `BaseExporter`
2. Implement `export()` method (required)
3. Implement `export_batch()` for efficiency (optional)
4. Add tests in `tests/unit/test_your_exporter.py`
5. Document usage in `docs/`

Example:

```python
from exporters.base import BaseExporter
from core.event import MCPEvent
from typing import List

class MyExporter(BaseExporter):
    async def export(self, event: MCPEvent) -> None:
        # Your implementation
        pass
    
    async def export_batch(self, event_batch: List[MCPEvent]) -> None:
        # Efficient batch handling
        pass
```

## Commit messages

Write clear, descriptive commit messages:

```
feat: Add new Redis exporter with connection pooling
fix: Correct timestamp formatting in file exporter
docs: Update configuration guide with examples
test: Add integration tests for Prometheus exporter
refactor: Simplify BaseExporter lifecycle methods
```

Use conventional commits:

- `feat:` — New feature
- `fix:` — Bug fix
- `docs:` — Documentation
- `test:` — Tests
- `refactor:` — Code refactoring
- `chore:` — Build, dependencies, etc.

## Pull request process

1. **Push to your fork**

   ```bash
   git push origin feature/my-feature
   ```

2. **Open a PR** against `main`

3. **Describe your changes**
   - What problem does it solve?
   - How does it work?
   - Any breaking changes?

4. **Tests must pass**
   - CI runs automatically on PRs
   - All tests must pass
   - Coverage should not decrease

5. **Request review**
   - At least one maintainer approval required
   - Address review feedback

6. **Merge**
   - Squash and merge to keep history clean
   - Maintainer will handle merging

## Documentation

### Code comments

```python
def _process_queue(self):
    """Process events from queue in batches."""
    # Wait up to 0.1s for new events
    while True:
        event = await asyncio.wait_for(self._queue.get(), timeout=0.1)
        # ...
```

### Docstrings

Use Google-style docstrings:

```python
def get_settings(self) -> AIMonitorSettings:
    """
    Retrieve the current AIMonitor settings.
    
    Returns:
        AIMonitorSettings instance with all configuration values
        
    Raises:
        ValueError: If configuration is invalid
    """
    pass
```

### Updating docs

- Update `docs/` markdown files
- Add examples to `docs/examples.md`
- Update `README.md` for major changes

## Testing guidelines

### Unit tests

Test individual components in isolation:

```python
@pytest.mark.asyncio
async def test_file_exporter_creates_file():
    exporter = FileExporter(base_uri=tmp_path)
    await exporter.connect()
    
    event = MCPEvent(...)
    await exporter.export(event)
    
    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
```

### Integration tests

Test components working together (marked with `@pytest.mark.integration`):

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_registry_with_multiple_exporters():
    # ...
    pass
```

### Coverage

Aim for >80% test coverage on new code:

```bash
pytest --cov=. tests/ --cov-report=html
```

## Performance considerations

- Batch processing is preferred over single-event processing
- Async operations should not block
- Minimize logging in hot paths
- Use connection pooling where applicable

## Security

- Never commit secrets (API keys, passwords)
- Use `.env.local` for local development
- Redact sensitive data in events
- Validate all external inputs
- Update dependencies regularly

```bash
# Check for vulnerable dependencies
pip-audit
```

## Release process

Maintainers only:

```bash
# Bump version in pyproject.toml
# Commit and push
git add pyproject.toml
git commit -m "Bump version to 0.2.0"
git tag v0.2.0
git push origin main --tags

# Build and upload
python -m build
python -m twine upload dist/*
```

## Getting help

- Open an [issue](https://github.com/franjefriten/AIMonitor/issues) for bugs
- Use [discussions](https://github.com/franjefriten/AIMonitor/discussions) for questions
- Check existing issues before opening new ones

## Recognition

Contributors are recognized in:

- `CONTRIBUTORS.md` (created per release)
- GitHub Insights
- Release notes

Thank you for contributing to AIMonitor! 🚀
