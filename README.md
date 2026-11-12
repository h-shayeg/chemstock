# ChemStock

[![CI](https://github.com/h-shayeg/chemstock/actions/workflows/ci.yml/badge.svg)](https://github.com/h-shayeg/chemstock/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12%2B-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A backend API for laboratory chemical inventories. It keeps track of chemicals and
their bottles, warns when incompatible chemicals are stored together, when bottles
expire and when stock runs low, and pulls GHS hazard data from PubChem.

Built with FastAPI, PostgreSQL and Docker, and covered by more than 650 tests that
run on every push.

## Features

- **Chemical catalog**: name, formula and CAS number (with check-digit validation),
  plus storage hazard classes such as `flammable`, `oxidizer` or `inorganic_acid`.
- **Inventory of bottles**: quantity and unit, storage location and expiry date.
- **Storage-compatibility checks**: every pair of bottles in the same place that
  should be stored apart, with a severity and the reasons. Missing hazard data is
  reported as `review_required`, never as safe.
- **Expiry alerts**: bottles that expire soon or have already expired.
- **Low-stock alerts**: chemicals whose bottles add up to their reorder level or
  less, with exact unit conversion (mg, g, kg, mL, L).
- **GHS hazard data from PubChem**: hazard statements, pictograms and signal word,
  cached in the database, with suggested hazard classes that a person confirms.
- **Authentication and roles**: JWT access tokens, Argon2 password hashing, four
  roles (viewer, member, admin, owner), admin permissions controlled by the owner,
  password changes that revoke old tokens, and rate limiting of password guessing.
- **Persian web pages (in progress)**: a right-to-left interface at `/ui` with
  Persian (Jalali) dates. It works without internet access: the style sheet and
  the font are served by the app itself. So far: login and a dashboard.

## Tech stack

Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.0, PostgreSQL 17, Alembic, PyJWT,
Argon2 (pwdlib), pytest, Ruff, Docker Compose and GitHub Actions (tests on Python
3.12 and 3.13 against a real PostgreSQL database).

## Design decisions

- **Domain logic is pure Python.** Storage rules, unit conversion and GHS parsing
  (`compatibility.py`, `storage.py`, `stock.py`, `ghs.py`) know nothing about HTTP or
  the database, so they are easy to read and to test.
- **Safe by default.** Unknown data is never treated as harmless, suggestions are
  never applied automatically, and only a person can mark a chemical as having no
  storage hazard.
- **Rules are enforced twice.** The API validates input, and the database has CHECK
  constraints for the same rules (units, roles, a reorder level with its unit, at most
  one owner), so bad data cannot get in another way.
- **Protected by default.** Whole routers need a login, and a test compares the real
  API with the documented access table, so a new endpoint cannot ship unprotected.
  Unknown usernames take as long to check as wrong passwords, and validation errors
  never echo a submitted password.
- **Honest tests.** They run against PostgreSQL (not SQLite), freeze the clock where
  dates matter, and never use the network: PubChem is replaced by fakes shaped like
  its real answers.

## Try it with Docker

```bash
cp .env.example .env
sed -i "s/^SECRET_KEY=$/SECRET_KEY=$(openssl rand -hex 32)/" .env   # signs login tokens
docker compose up --build -d
docker compose exec api python -m chemstock.cli create-user alice --role admin  # asks for a password
docker compose exec api python -m chemstock.cli seed-demo                       # example lab data
```

Open <http://localhost:8000/ui> for the Persian web pages (log in as `alice`), or
<http://localhost:8000/docs> for the API: click **Authorize** and log in. Then
try `GET /storage-conflicts`, `GET /inventory-items/expiring`,
`GET /chemicals/low-stock`, and `GET /chemicals/3/ghs` (toluene, which has no hazard
classes yet: PubChem suggests `flammable`).

`seed-demo` only fills an empty database. Stop everything with `docker compose down`
(add `-v` to delete the data too).

## Local development

Create `.env` as shown above, then:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
docker compose up -d db          # PostgreSQL on localhost:5433
alembic upgrade head
pytest
ruff check .
uvicorn chemstock.main:app --reload
```

The tests create and use their own database (`chemstock_test`), never the
development one.

## API overview

| Endpoint | What it does |
|---|---|
| `POST /auth/login`, `GET /auth/me`, `POST /auth/change-password` | log in, who am I, change password |
| `/users`, `PUT /users/{id}/permissions` | user management (admins and the owner) |
| `/chemicals` (`GET`, `POST`, `PATCH`, `DELETE`) | the chemical catalog |
| `PUT /chemicals/{id}/hazard-classes` | set the hazard classes of a chemical |
| `GET /chemicals/{id}/ghs` | GHS hazard data from PubChem, with suggestions |
| `GET /chemicals/low-stock` | chemicals at or below their reorder level |
| `/inventory-items` (`GET`, `POST`, `PATCH`, `DELETE`) | bottles |
| `GET /inventory-items/expiring` | bottles that expire soon or have expired |
| `GET /storage-conflicts` | bottles stored together that should be apart |
| `GET /hazard-classes` | every hazard class and what it means |
| `GET /health` | health check (no login needed) |

The full, interactive documentation is generated by FastAPI at `/docs`.

## Project structure

```text
src/chemstock/
  main.py            the FastAPI app
  routers/           HTTP endpoints, one module per resource
  web/               Persian web pages: routes, templates, style sheet and font
  reports.py         low-stock and storage-conflict reports (API and web pages)
  jalali.py          Persian dates and digits for the web pages
  models.py          database tables (SQLAlchemy)
  schemas.py         request and response models (Pydantic)
  compatibility.py   storage rules between hazard classes
  storage.py         finds conflicting bottles in the same location
  stock.py           unit conversion and low-stock detection
  ghs.py             reads PubChem's GHS data, suggests hazard classes
  pubchem.py         small HTTP client for PubChem
  ghs_cache.py       caches PubChem answers in the database
  users.py, security.py, tokens.py, permissions.py, throttle.py   accounts and login
  cli.py, demo.py    command line tools and example data
migrations/          Alembic database migrations
tests/               pytest tests (and sample PubChem answers in tests/data)
```

## Safety note

The storage-compatibility checks are an assistive tool, not a replacement for the
Safety Data Sheet (SDS) or your institution's safety rules. Hazard classes are a
simplification and are entered by people. A chemical without a classification is
reported as `review_required`, never as safe.

Once a person has checked a chemical and found nothing that matters for storage
separation (water, for example), they can give it the class `no_storage_hazard`.
Only a person can choose it: it is never suggested automatically, and it cannot
be combined with other classes.

## Low-stock alerts

Give a chemical a reorder level, for example 1 L of acetone, with
`reorder_level` and `reorder_unit` (in `POST /chemicals`, or both together in
`PATCH /chemicals/{id}`; both `null` removes it). `GET /chemicals/low-stock` then
lists every chemical whose bottles add up to that amount or less, the emptiest
first. A chemical with no bottles left has a total of 0.

Bottles are converted to the unit of the reorder level, so 300 mL and 0.2 L add up
to 0.5 L. Mass and volume cannot be added without the density, so a bottle in a
unit of the other kind (grams for a level in litres) is left out of the total and
counted in `uncounted_item_count`. Such a bottle can cause a false alarm, but it
never hides a real one.

## Hazard data from PubChem

`GET /chemicals/{id}/ghs` looks up the chemical's CAS number in
[PubChem](https://pubchem.ncbi.nlm.nih.gov/) and returns its GHS classification:
hazard statements (H codes), pictograms, signal word and the sources that
classified it. PubChem collects classifications from several sources; ChemStock
shows the union of what they report, because for storage a missed hazard is worse
than one too many.

The answer also has `suggested_hazard_classes` for the storage-compatibility checks.
They are only suggestions: nothing changes until a person sets the classes with
`PUT /chemicals/{id}/hazard-classes`.

| GHS codes | Suggested class |
|---|---|
| H220 to H228 | `flammable` |
| H270, H271, H272 | `oxidizer` |
| H260, H261, EUH014, EUH029 | `water_reactive` |
| EUH031, EUH032 | `acid_gas_generator` |
| H200 to H208, H240, H241, H250 | `isolate` |

Acids, bases, active metals and halogenated solvents cannot be recognized from GHS
codes (a corrosive H314 can be either an acid or a base), so they are never
suggested, and neither is `no_storage_hazard`.

Answers are stored in the database for `PUBCHEM_CACHE_DAYS` days (default 30), so
PubChem is asked once per CAS number and period. If PubChem cannot be reached, the
last stored answer is returned with `"stale": true`; if nothing is stored yet, the
API answers `503`. The tests never use the network.

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

## Web pages

The pages under `/ui` use the same users, roles and reports as the API. After
logging in, the access token is kept in a cookie that page scripts cannot read
(`HttpOnly`) and that other sites cannot use (`SameSite=Strict`). A web login lasts
`WEB_SESSION_HOURS` hours (default 8); changing the password or deactivating the
account ends it at once, exactly like an API token. Pages are never cached and
load nothing from other sites.

The font is [Vazirmatn](https://github.com/rastikerdar/vazirmatn) by Saber
Rastikerdar, under the SIL Open Font License 1.1 (see
`src/chemstock/web/static/fonts/OFL.txt`).

## License

[MIT](LICENSE), by Hadi Shayeg ([@h-shayeg](https://github.com/h-shayeg)).
