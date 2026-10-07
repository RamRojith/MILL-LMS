# MILL LMS - Safety & Production Learning Management System

A secure, role-based LMS for a spinning mill organization with 8 units, safety training monitoring, 16-level sequential learning, MCQ-based progression, and corporate/unit/operator dashboards.

## Run Locally

```powershell
python app.py
```

Open:

```text
http://127.0.0.1:8000
```

The app creates and seeds `data/mill_lms.db` on first run.

## Demo Credentials

All demo passwords:

```text
demo123
```

Users:

- `CORP001` - Corporate Safety Head
- `RMLH001` - Function Safety Unit Head, RML
- `RSTH001` - Function Safety Unit Head, RST
- `RMUH001` - Function Safety Unit Head, RMU
- `EMP001` - Operator, RML, current Level 05
- `EMP101` - Operator, RST
- `EMP201` - Operator, RMU

## Project Structure

```text
app.py              Backend: schema, seed, auth, RBAC, LMS engine, analytics, reports, HTTP server
static/index.html   SPA shell
static/app.js       Role-based frontend (dashboards, roadmap, learning flow, reports)
static/styles.css   Design system
tests/test_backend.py  35 automated tests (RBAC, isolation, progression, reports)
docs/architecture.md    Full system design
data/mill_lms.db    SQLite database (created on first run)
```

## Run Tests

```powershell
python -m unittest discover -s tests -v
```

## API Map

| Method | Endpoint | Access |
| --- | --- | --- |
| POST | `/api/login` | Public |
| POST | `/api/logout` | Authenticated |
| GET | `/api/me`, `/api/my-profile`, `/api/my-roadmap`, `/api/my-progress`, `/api/my-assessments` | Operator |
| GET | `/api/my-module/{level}` | Operator (locked level -> 403, no content leak) |
| POST | `/api/my-module/{level}/content-complete`, `/video-progress`, `/assessment-start`, `/assessment-submit` | Operator (current level only) |
| GET | `/api/unit/dashboard`, `/api/unit/progress`, `/api/unit/at-risk`, `/api/unit/employees` | Unit Head (own unit only) |
| GET | `/api/corporate/dashboard`, `/api/units`, `/api/units/{code}`, `/api/units/{code}/dashboard` | Corporate |
| GET | `/api/employees`, `/api/employees/{id}` | Corporate |
| GET | `/api/analytics`, `/api/progress`, `/api/at-risk`, `/api/audit-logs` | Corporate |
| GET | `/api/reports?scope=employee\|module&format=json\|csv` | Corporate (unit heads scoped to own unit) |
| GET | `/api/health` | Public |

Filters: `unit`, `status`, `level`, `date_from`, `date_to`, `action`, `employee_id`.

## Configuration

| Env var | Default | Purpose |
| --- | --- | --- |
| `PORT` | `8000` | HTTP port |
| `MILL_LMS_DB` | `data/mill_lms.db` | SQLite path (tests use a temp DB) |

## Security Model

- Backend-enforced RBAC.
- Backend-enforced unit access.
- Backend-enforced object access.
- Backend-enforced module locking.
- Server-side session storage.
- PBKDF2 password hashing.
- Activity audit logs.

See `docs/architecture.md` for the full system design.
