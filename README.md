# ChemStock

[![CI](https://github.com/h-shayeg/chemstock/actions/workflows/ci.yml/badge.svg)](https://github.com/h-shayeg/chemstock/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12%2B-blue)

Backend API for tracking laboratory chemicals, storage locations and hazard data,
with storage-compatibility checks. Built with FastAPI and Docker.

> **Status:** early development. See the [roadmap](#roadmap) for what is done and what is planned.

## Quick start

### With Docker

```bash
cp .env.example .env        # optional: set PIP_INDEX_URL to a PyPI mirror
docker compose up --build
curl http://localhost:8000/health
```

### Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check .
uvicorn chemstock.main:app --reload
```

Interactive API docs are available at `http://localhost:8000/docs`.

## Project structure

```text
src/chemstock/   application code
tests/           pytest tests
```

## Roadmap

- [x] Project skeleton and tooling (ruff, pytest)
- [x] Health check endpoint
- [x] Docker and Docker Compose
- [x] CI with GitHub Actions
- [x] PostgreSQL, SQLAlchemy and Alembic migrations
- [ ] Chemical inventory CRUD (name, CAS number, quantity, location, expiry date)
- [ ] Authentication and roles
- [ ] PubChem integration for hazard (GHS) data, with caching
- [ ] Storage-compatibility checks
- [ ] Expiry and low-stock alerts
