# Contributing to Memory Thread

Thank you for your interest in contributing to Memory Thread! This document provides guidelines and best practices for contributing.

## Getting Started

### 1. Fork and Clone

```bash
git clone https://github.com/YOUR_USERNAME/MemoryThread.git
cd MemoryThread
```

### 2. Set Up Development Environment

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install with dev dependencies
pip install -e .[dev]
```

### 3. Verify Setup

```bash
pytest tests/test_sdk.py -v
```

---

## Development Workflow

### Branch Naming

- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation
- `refactor/description` - Code refactoring

### Code Style

We use:

- **Black** for formatting
- **Ruff** for linting
- **MyPy** for type checking

```bash
# Format code
black memory_thread/

# Lint
ruff check memory_thread/

# Type check
mypy memory_thread/
```

### Testing

All changes must have tests:

```bash
# Run all tests
pytest

# With coverage
pytest --cov=memory_thread --cov-report=html

# Specific test
pytest tests/test_sdk.py::TestRemember -v
```

---

## Pull Request Process

1. **Create a branch** from `main`
2. **Write tests** for your changes
3. **Ensure all tests pass**
4. **Update documentation** if needed
5. **Submit PR** with clear description

### PR Checklist

- [ ] Tests pass locally (`pytest`)
- [ ] Code is formatted (`black .`)
- [ ] No lint errors (`ruff check .`)
- [ ] Documentation updated (if applicable)
- [ ] Commit messages are clear

---

## Code Architecture

### Key Directories

| Directory                 | Purpose               |
| ------------------------- | --------------------- |
| `memory_thread/sdk.py`    | Main SDK entry point  |
| `memory_thread/services/` | Core business logic   |
| `memory_thread/nervous/`  | Security, RBAC, vault |
| `memory_thread/api/`      | REST API              |
| `tests/`                  | Test suite            |

### Adding New Features

1. **Services**: Add to `memory_thread/services/`
2. **API Endpoints**: Add to `memory_thread/api/server.py`
3. **TUI Commands**: Add to `memory_thread/utils/cli_bridge.py`
4. **Tests**: Add to `tests/test_*.py`

---

## Documentation

- **Code**: Use docstrings (Google style)
- **README**: Update for user-facing changes
- **API**: Pydantic models auto-generate OpenAPI docs

---

## Questions?

Open an issue or reach out to the maintainers.

Thank you for contributing! 🚀
