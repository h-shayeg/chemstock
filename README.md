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
- [x] User management API with an owner (create users, change roles, deactivate)
- [x] Admin permissions controlled by the owner (create users, change roles, deactivate users)
- [x] Users change their own password (older tokens stop working)
- [x] Rate limiting of failed login and password-change attempts
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
| `admin` | everything a member can do, plus manage `member` and `viewer` accounts |
| `owner` | the one main admin: everything, and the only one who manages admins |

Create the first admin, log in, and call the API:

    python -m chemstock.cli create-user alice --role admin    # asks for the password
    curl -s -X POST localhost:8000/auth/login -d "username=alice" -d "password=..."
    curl -s localhost:8000/chemicals -H "Authorization: Bearer <access_token>"

The interactive docs at `/docs` have an **Authorize** button for the same login.
Roles are read from the database on every request, so deactivating a user or
changing a role takes effect immediately.

### Managing users

Admins and the owner use `/users` (`POST`, `GET`, `PATCH`). Everyone may only change
accounts that rank strictly below their own, and may only hand out roles strictly
below their own. So admins manage members and viewers, and only the owner manages
admins. Nobody changes their own role or status, and users are deactivated, never
deleted.

The owner role cannot be given through the API. Promote an existing user from the
command line (the previous owner, if any, becomes an admin):

    python -m chemstock.cli set-owner alice

### Changing your password

`POST /auth/change-password` with `current_password` and `new_password`. Afterwards
every access token issued before the change stops working, so log in again.

### Rate limiting

Failed password guesses are limited, for `POST /auth/login` and for the current
password in `POST /auth/change-password`: at most 5 per username and client address,
and 20 per client address in total, within 15 minutes. Beyond that the API answers
`429` with a `Retry-After` header and does not even check the password, so a correct
guess during a lockout is refused too. A successful login clears the counter. Limits
are configurable (`LOGIN_MAX_ATTEMPTS_PER_USERNAME`, `LOGIN_MAX_ATTEMPTS_PER_IP`,
`LOGIN_LOCKOUT_MINUTES`).

The client address is the one the server sees. Behind a reverse proxy, run uvicorn
with `--proxy-headers` and `--forwarded-allow-ips` set to the proxy; otherwise all
users share the proxy's address.

### Admin permissions

The owner decides what each admin may do in user management. There are three
permissions: `create_users`, `change_roles` and `deactivate_users`. A new admin has
all three. Only the owner changes them, with `PUT /users/{id}/permissions` and the
full list of what the admin is allowed (an empty list takes everything away). The
owner always has every permission, and reading users is never restricted. Every user
is returned with its current `permissions`, also in `GET /auth/me`. Changes take
effect immediately, and restrictions are remembered if an admin is moved to another
role and back.

What is stored is the list of permissions that were taken away. So a permission that
is added in the future is granted to every admin unless its migration says otherwise.
