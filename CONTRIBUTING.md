# Contributing to ScoreOCR Toolkit

Thank you for your interest in contributing! This document outlines the process for contributing to this project.

## Code of Conduct

By participating, you are expected to uphold our [Code of Conduct](CODE_OF_CONDUCT.md). Please report unacceptable behavior to the maintainers.

## How to Contribute

### Reporting Bugs

1. Check [existing issues](https://github.com/Jimmy-hankdress/score-ocr-toolkit/issues) first
2. Create a new issue with:
   - Clear title and description
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment (OS, Python version, Docker/venv)
   - Sample files if applicable (remove sensitive data)

### Suggesting Features

1. Check [roadmap](README.md#roadmap) and existing issues
2. Open a feature request issue with:
   - Use case and motivation
   - Proposed solution
   - Alternatives considered

### Pull Request Process

1. **Fork** the repository
2. **Create a branch**: `git checkout -b feature/your-feature-name` or `fix/issue-number`
3. **Make changes** following the coding standards below
4. **Test locally**:
   ```bash
   # Run all checks
   ruff check . --fix
   ruff format .
   mypy --explicit-package-bases src/ app.py
   pytest tests/ -v --asyncio-mode=auto
   ```
5. **Commit** with conventional commits:
   - `feat: add new feature`
   - `fix: resolve issue #123`
   - `docs: update README`
   - `chore: update dependencies`
   - `refactor: restructure module`
   - `test: add unit tests`
6. **Push** and open a Pull Request

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR-USERNAME/score-ocr-toolkit.git
cd score-ocr-toolkit

# Create virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# Optional: Install HOMR for OMR testing
pip install "homr[cpu]"

# Install pre-commit hooks
pre-commit install
```

## Coding Standards

### Python Style

- **Formatter**: Ruff (line-length=100, double quotes)
- **Linter**: Ruff (select=E,W,F,I,B,C4,UP)
- **Type Checker**: MyPy (strict for `src.ocr.*`)
- **Target**: Python 3.11+

### Code Patterns

1. **FastAPI Endpoints**:
   - Use Pydantic `BaseModel` for requests
   - Return type annotations: `JSONResponse | ResponseModel`
   - No `response_model` on union returns
   - Standardized error format via `HTTPException`

2. **Async Operations**:
   - Blocking calls → `asyncio.to_thread()`
   - External processes → timeout handling
   - Structured logging at decision points

3. **MusicXML Generation**:
   - Delegate pitch parsing to `jianpu_converter.parse_pitch()`
   - Use `divisions=8` (32nd note = 1)
   - Never hand-parse pitch strings

4. **Configuration**:
   - All magic numbers in `src/ocr/config.py`
   - Environment variables via `AppConfig.from_env()`

5. **Logging**:
   - Use `get_logger(__name__)` in each module
   - JSON formatter in production
   - `logger.exception()` in except blocks

### Testing Requirements

- **Unit tests** (`tests/unit/`): Pure functions, no external deps
- **Integration tests** (`tests/integration/`): API endpoints via `httpx.ASGITransport`
- **Async tests**: Use `@pytest_asyncio.fixture` and `asyncio_mode = auto`
- **Coverage**: Aim for >80% on core modules
- **Run**: `pytest tests/ -v --asyncio-mode=auto --cov=src --cov-report=term-missing`

### Git Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`, `ci`, `build`

Examples:
```
feat(api): add batch PDF processing endpoint
fix(musicxml): resolve double flat parsing for Dbb2
docs(readme): add Docker deployment guide
test(jianpu): add enharmonic equivalence test cases
```

## Architecture Overview

```
app.py (FastAPI routes)
    │
    ├── /recognize → format_importer → (text) OR homr_recognizer → Symbol[]
    │
    ├── /api/convert-to-jianpu → jianpu_converter → JianpuResult
    │
    ├── /api/export-jianpu → jianpu_converter → text file
    │
    └── /api/export-musicxml → musicxml_builder → MusicXML file
```

### Core Modules

| Module | Responsibility |
|--------|----------------|
| `config.py` | Centralized configuration, env vars |
| `logging_config.py` | Structured logging setup |
| `recognizer.py` | `Symbol` dataclass, `BaseRecognizer` ABC |
| `homr_recognizer.py` | Async HOMR subprocess wrapper |
| `format_importer.py` | PDF/DOCX/TXT/JSON/image → symbols |
| `jianpu_converter.py` | Pitch↔jianpu, transposition, measure layout |
| `note_extractor.py` | OpenCV notehead contour extraction |
| `musicxml_builder.py` | Symbols → MusicXML 4.0 |

## Security

- No API keys, tokens, or credentials in code
- File upload: size limit, extension whitelist, path sanitization
- Error responses: no stack traces to clients
- HOMR AGPL-3.0 isolated via subprocess

## Release Process

Maintainers only:

```bash
# 1. Update version in pyproject.toml
# 2. Update CHANGELOG.md
# 3. Commit: git commit -m "chore: release vX.Y.Z"
# 4. Tag: git tag -a vX.Y.Z -m "Release vX.Y.Z"
# 5. Push: git push origin main --tags
# 6. GitHub Actions builds Docker image automatically
```

## Questions?

Open a [discussion](https://github.com/Jimmy-hankdress/score-ocr-toolkit/discussions) or issue.