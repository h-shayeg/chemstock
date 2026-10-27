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
- [x] Chemical catalog CRUD (name, CAS number, formula)
- [x] Inventory items (bottles): quantity, storage location, expiry date
- [x] Authentication: login with JWT access tokens, role-based access (admin / member / viewer)
- [ ] User management API (create users, change roles, deactivate)
- [ ] PubChem integration for hazard (GHS) data, with caching
- [x] Storage-compatibility checks (hazard classes, rules, `/storage-conflicts`)
- [x] Expiry alerts: bottles expiring soon or already expired
- [ ] Low-stock alerts

## Safety note

The storage-compatibility checks are an assistive tool, not a replacement for the
Safety Data Sheet (SDS) or your institution's safety rules. Hazard classes are a
simplification and are entered by people. A chemical without a classification is
reported as `review_required`, never as safe.

## Authentication

Every endpoint except `GET /health` and `POST /auth/login` needs an access token.

| Role | May do |
|---|---|
| `viewer` | read everything |
| `member` | read and change chemicals, hazard classes and inventory items |
| `admin` | everything a member can do (user management API: coming next) |

Create the first admin, log in, and call the API:

    python -m chemstock.cli create-user alice --role admin    # asks for the password
    curl -s -X POST localhost:8000/auth/login -d "username=alice" -d "password=..."
    curl -s localhost:8000/chemicals -H "Authorization: Bearer <access_token>"

The interactive docs at `/docs` have an **Authorize** button for the same login.
Roles are read from the database on every request, so deactivating a user or
changing a role takes effect immediately.
