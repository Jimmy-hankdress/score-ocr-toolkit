# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.0.0] - 2026-10-26

### Added
- **Full SheetMusicOMR v3.00 Integration** (`app/`, `web/`): Multi-stage OMR task pipeline, SQLite project & self-learning store, ChordPro bidirectional sync, guitar/ukulele chord diagram libraries, URL score import (`POST /api/import-url`), and multi-format export (MusicXML, MIDI, PDF, Word, Sola321, TXT).
- **Score Studio Professional Editor** (`app/scorestudio/`, `web/score-studio/`): Event-driven structured score editor with Command Stack undo/redo, real-time measure validation, chord track alignment, and multi-line lyrics editing.
- **Default Professional Edit Mode**: Automatically opens `Score Studio` (`#sola321-pane` / `/editor/studio/{doc_id}`) by default on startup and loads the target or latest project.
- **One-Click SQLite Project Import (`POST /api/import-from-canvas`)**: Converts recognized symbols into `ScoreDocument` measures, saves directly to the main SQLite project list, and returns Score Studio links.

### Changed
- **Removed Deprecated Canvas Visual Proofreader**: Removed the standalone `/canvas-editor` (`static/index.html`) UI and topbar navigation links in favor of the unified SheetMusicOMR v3.00 workbench and Score Studio professional editor.
- **Fixed Windows `run.bat` Launcher**: Enforced CRLF line endings via `.gitattributes` and pure-ASCII batch syntax to prevent CMD encoding parse errors when double-clicking `run.bat`.

## [1.1.0] - 2026-10-24

### Added
- **Configuration Management** (`src/ocr/config.py`): Centralized `AppConfig` dataclass with environment variable support via Pydantic Settings
- **Structured Logging** (`src/ocr/logging_config.py`): JSON formatter, configurable log levels, replaces all `print()` statements
- **File Upload Validation**: 50MB size limit, extension whitelist (PDF, DOCX, TXT, JSON, BMP, PNG, JPG, WebP, TIFF), path traversal protection
- **Pydantic Request Models**: All endpoints use `BaseModel` with `field_validator` for input validation
- **Standardized Error Responses**: Consistent format with `error_type`, `friendly_error`, `suggestion`, `status_code`
- **Async HOMR Recognizer**: Non-blocking `asyncio.to_thread` with 120s timeout, fallback CLI detection
- **MusicXML Double Accidentals Support**: `##` → `alter=2`, `bb` → `alter=-2` via unified `parse_pitch()`
- **Module-Level Parser Reference**: `import src.ocr.jianpu_converter as jianpu_converter` prevents stale binding after hot-reload
- **MusicXML Divisions=8**: Quarter note = 8, 32nd note = 1 (minimum unit), supports all standard durations
- **Comprehensive Test Suite** (150 tests):
  - Unit tests: 128 tests (`test_jianpu_converter.py` 75, `test_musicxml_builder.py` 31, `test_format_importer.py` 22)
  - Integration tests: 22 API endpoint tests via `httpx.ASGITransport`
- **GitHub Actions CI Pipeline** (`.github/workflows/ci.yml`): 5 jobs (lint → type-check → unit-test → integration-test → build → docker)
- **Docker Multi-Stage Build** (`Dockerfile`): builder → runtime/dev/test targets
- **Docker Compose Profiles** (`docker-compose.yml`): dev (hot reload), test, prod (with nginx)
- **Production Nginx Config** (`nginx.conf`): SSL, static caching, security headers, rate limiting
- **Pre-commit Hooks** (`.pre-commit-config.yaml`): ruff, mypy, bandit, trailing-whitespace, end-of-file-fixer
- **pyproject.toml**: Unified tool config for pytest, ruff, mypy, coverage
- **Package Exports** (`src/ocr/__init__.py`): Public API exports for `Symbol`, `AppConfig`, `get_logger`, etc.
- **README Overhaul**: Architecture diagram, Docker deployment, CI/CD badge, config docs, API examples, jianpu format tables

### Changed
- **app.py Complete Rewrite**: Lifespan management, async HOMR, Pydantic models, error handling, file validation
- **homr_recognizer.py**: Migrated to async, timeout handling, config-driven, structured logging
- **musicxml_builder.py**: Rewritten with module-level parser, divisions=8, double sharp/flat support
- **jianpu_converter.py**: Extended `PITCH_SEMITONES` and `SEMITONE_TO_JIANPU` for double accidentals
- **note_extractor.py**: Integrated structured logging
- **requirements.txt**: Added pytest, pytest-asyncio, httpx, pytest-cov, ruff, mypy, python-json-logger

### Fixed
- **Double Sharp/Flat Parsing**: `F##5` → alter=2/octave=5, `Dbb2` → alter=-2/octave=2 (was producing invalid octave strings)
- **Module Caching**: Hot-reload fixes now apply immediately via module import pattern
- **Mypy Type Errors**: Added type hints, `type: ignore` for missing stubs (pypdfium2, pythonjsonlogger), fixed indentation
- **Pydantic v2 Migration**: `@validator` → `@field_validator` + `@classmethod`, `min_items` → `min_length`
- **Return Type Annotations**: Removed conflicting `response_model` from union return endpoints
- **Ruff Import Order**: Consolidated all imports at module top, removed duplicates
- **Async Fixture RuntimeError**: Added `pytest_asyncio` and `asyncio_mode = auto`

### Security
- File upload size limit (50MB default, configurable via `SCOREOCR_MAX_UPLOAD_MB`)
- Extension whitelist prevents executable uploads
- Path traversal protection on download endpoint (regex sanitization)
- Error responses exclude stack traces from client

## [1.0.0] - 2026-10-20

### Added
- **FastAPI Server** with OpenCV preprocessing pipeline
- **Pluggable OMR Interface** with external HOMR subprocess isolation (AGPL-3.0 contained)
- **Notehead Contour Extraction** with coordinate pairing
- **HTML5 Canvas Visual Editor**: pan, zoom, drag note boxes, resize corners
- **Multi-format Input**: PDF (pypdfium2), DOCX (image extraction), TXT, JSON, BMP, PNG, JPG
- **Jianpu Engine**: Transposition (1=C/D/G/F/Bb), octave dots, time signature auto-measure lines
- **Canvas Jianpu Badges**: Green numbered notation labels on noteheads
- **Virtual Piano Keyboard**: CDEFGAB, accidentals, duration switches, add/delete notes
- **Dual Export**: MusicXML 4.0 (MuseScore/Finale compatible) + plain text jianpu
- **Favicon & Error Handling**: Eliminated 404/422 errors for non-staff scores
- **End-to-End Tests**: All HTTP endpoints returning 200 OK

### Architecture Decisions
- **MIT License** for core project (commercial-friendly)
- **HOMR AGPL-3.0** isolated via subprocess (no license infection)
- **Local-first**: No external API dependencies for core functionality

## [Unreleased]

### Planned (Roadmap)
- Multi-page PDF batch processing with page navigation
- Tone.js / MIDI real-time playback with cursor following
- RapidOCR lyrics recognition with X-axis note alignment
- SVG/PDF vector jianpu export for print-quality output

---

## Version History

| Version | Date | Commit | Description |
|---------|------|--------|-------------|
| 1.1.0 | 2026-10-24 | `1fbe576` | Phase 2+3: Tests, CI/CD, Docker, Docs |
| 1.0.0 | 2026-10-20 | `e6a7bcb` | MVP: Complete OMR + Jianpu pipeline |

## Release Process

```bash
# 1. Update version in pyproject.toml
# 2. Update CHANGELOG.md with release notes
# 3. Commit: git commit -m "chore: release vX.Y.Z"
# 4. Tag: git tag -a vX.Y.Z -m "Release vX.Y.Z"
# 5. Push: git push origin main --tags
# 6. GitHub Actions builds Docker image automatically
```