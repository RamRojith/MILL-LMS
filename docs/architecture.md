# MILL LMS - Safety & Production Learning Management System

Pre-code architecture baseline and living design reference. Built from the attached reference deck: one secure platform, role-based access, unit authorization, a 16-level production roadmap, Content -> Video -> MCQ, backend-validated unlocks, progress analytics, and at-risk identification.

---

## 1. Complete System Architecture

```text
LAYER 1 - USERS
  Corporate Safety Head (all 8 units)
  Function Safety Unit Head (one unit)
  Operator / Workman (self only)
        |
LAYER 2 - AUTHENTICATION & AUTHORIZATION
  Employee ID + password login -> PBKDF2 verify -> server-side session token
  Role identification -> unit identification -> RBAC guard -> unit guard
  -> object guard -> module guard -> audit log of violations
        |
LAYER 3 - LMS ENGINE
  16-level roadmap resolver -> module state (COMPLETED / CURRENT / LOCKED)
  -> sequential progression rules -> backend unlock enforcement
        |
LAYER 4 - LEARNING & ASSESSMENT
  Learning content (SOP/docs) -> training video (start/progress/complete)
  -> MCQ assessment -> automatic scoring -> pass/fail -> retake policy
        |
LAYER 5 - DATABASE (SQLite / relational, one platform, one database)
  roles, units, users, modules, learning_contents, videos, assessments,
  questions, learning_progress, assessment_attempts, activity_logs, sessions
        |
LAYER 6 - ANALYTICS & DASHBOARDS
  Corporate dashboard, unit dashboard, operator dashboard,
  analytics, reports (JSON + CSV), audit logs
```

Core principle: **one LMS platform, one authentication system, one relational database.** No per-unit systems. Role and unit scope are derived from the authenticated server-side session record on every request; the frontend never supplies identity.

## 2. Role-Permission Matrix

| Capability | Corporate Safety Head | Function Safety Unit Head | Operator / Workman |
|---|---:|---:|---:|
| Login / logout / session | Yes | Yes | Yes |
| View unit master (all 8 units) | Yes | Own unit only | No |
| View all employees | Yes | No | No |
| View unit employees | Yes | Assigned unit only | No |
| Employee detail + roadmap + history | Any employee | Assigned unit operators only | Blocked (own profile only) |
| Corporate KPIs / analytics | Yes | No | No |
| Unit KPIs / funnel / progress | All units | Assigned unit only | No |
| At-risk employee list | All units | Assigned unit only | No |
| Reports (JSON + CSV) | All units | Assigned unit only | No |
| Audit / activity logs | Yes | No | No |
| Own profile / roadmap / progress / assessments | Yes | Yes | Yes |
| Complete content / video / assessment | No | No | Own unlocked modules only |
| Unlock next module | Backend validation only | Backend validation only | Backend validation only |

## 3. Unit Access-Control Matrix

Units: RML, RST, RMU, RMF, SAN, SRS, SVSM, RTL-S.

| User Type | RML | RST | RMU | RMF | SAN | SRS | SVSM | RTL-S |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Corporate Safety Head | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| RML Unit Head | Yes | No | No | No | No | No | No | No |
| RST Unit Head | No | Yes | No | No | No | No | No | No |
| RMU Unit Head | No | No | Yes | No | No | No | No | No |
| (same pattern for RMF, SAN, SRS, SVSM, RTL-S heads) | No | No | No | Own | No | No | No | No |
| Operator / Workman | Own | Own | Own | Own | Own | Own | Own | Own |

Enforcement points (all server side):

1. `GET /api/units/RST/dashboard` as an RML head -> `403 UNIT_FORBIDDEN` + `UNAUTHORIZED_ACCESS_ATTEMPT` log entry. Changing the URL manually changes nothing.
2. `GET /api/employees?unit=RST` as an RML head -> `403 UNIT_FORBIDDEN`. Unit Head requests may only name their own unit; omitting the parameter scopes to their own unit automatically.
3. `GET /api/employees/EMP101` (RST) as an RML head -> `403 EMPLOYEE_FORBIDDEN`.
4. Any operator calling `/api/employees*`, `/api/units*`, `/api/audit-logs`, `/api/reports`, `/api/analytics` -> `403 FORBIDDEN`.
5. Identity always comes from the session row in the database, never from a request header, body field, or frontend state.

## 4. Database ER Structure

```text
roles 1 --- n users
units 1 --- n users            (users.unit_id, operators and unit heads)
units 1 --- n modules          (unit_id, level_number UNIQUE 1..16)
modules 1 --- 1 learning_contents
modules 1 --- 1 videos
modules 1 --- 1 assessments
assessments 1 --- n questions
users 1 --- n learning_progress      (user_id + module_id UNIQUE)
users 1 --- n assessment_attempts    (attempt-level score history)
users 1 --- n activity_logs
users 1 --- n sessions
units n --- 1 users             (units.safety_head_id -> unit head user)
```

Tables:

- `roles(id, role_name)`
- `units(id, unit_code, unit_name, safety_head_id, status)`
- `users(id, employee_id, name, username, password_hash, role_id, unit_id, status, created_at, last_login)`
- `modules(id, unit_id, level_number, title, description, status)` — UNIQUE(unit_id, level_number)
- `learning_contents(id, module_id, content, document_url, completion_required)`
- `videos(id, module_id, video_url, duration_seconds, completion_required)`
- `assessments(id, module_id, pass_percentage, attempt_limit)`
- `questions(id, assessment_id, question, option_a..option_d, correct_answer)`
- `learning_progress(id, user_id, module_id, content_completed, video_started, video_progress, video_completed, assessment_completed, score, attempts, status, started_at, completed_at, last_activity_at)` — UNIQUE(user_id, module_id)
- `assessment_attempts(id, user_id, module_id, attempt_no, score, passed, answers, created_at)`
- `activity_logs(id, user_id, action, module_id, metadata, ip_address, session_id, timestamp)`
- `sessions(id, user_id, session_token_hash, expires_at, created_at)`

Status values: `learning_progress.status` in `LOCKED | CURRENT | COMPLETED | FAILED`; `training_status` (derived) in `ON TRACK | NEEDS ATTENTION | INACTIVE | COMPLETED`.

## 5. API Structure

Base: `/api`. All routes require a valid session cookie except `POST /api/login`. Errors return `{"error": CODE, "message": "..."}`.

Authentication:

| Method | Route | Access | Notes |
|---|---|---|---|
| POST | `/api/login` | Public | `{employee_id, password}` -> sets HttpOnly session cookie, brute-force throttled |
| POST | `/api/logout` | Session | Destroys server-side session, clears cookie |
| GET | `/api/me` | Session | Current user identity |

Management (Corporate + Unit Head, unit-scoped):

| Method | Route | Access |
|---|---|---|
| GET | `/api/corporate/dashboard` | Corporate only |
| GET | `/api/analytics` | Corporate only |
| GET | `/api/units` | Corporate only (unit master + performance) |
| GET | `/api/units/{unit_code}` | Corporate or head of that unit |
| GET | `/api/units/{unit_code}/dashboard` | Corporate or head of that unit |
| GET | `/api/units/{unit_code}/employees?status=&q=&level=` | Corporate or head of that unit |
| GET | `/api/units/{unit_code}/progress` | Corporate or head of that unit (level funnel) |
| GET | `/api/unit/dashboard` | Assigned unit head |
| GET | `/api/unit/progress` | Assigned unit head |
| GET | `/api/employees?unit=&status=&q=&level=&min_progress=` | Corporate (any) / head (own unit forced) |
| GET | `/api/employees/{employee_id}` | Corporate (any) / head (own unit operators) |
| GET | `/api/at-risk?unit=` | Corporate (all) / head (own unit) |
| GET | `/api/reports?unit=&status=&level=&from=&to=&scope=&format=` | Corporate (all) / head (own unit); `format=csv` download |
| GET | `/api/audit-logs?action=&employee_id=&limit=` | Corporate only |

Operator (self only):

| Method | Route | Access |
|---|---|---|
| GET | `/api/my-profile` | Operator |
| GET | `/api/my-roadmap` | Operator |
| GET | `/api/my-progress` | Operator |
| GET | `/api/my-assessments` | Operator |
| GET | `/api/my-module/{level}` | Operator, level must be unlocked (else 403 `MODULE_LOCKED`) |
| POST | `/api/my-module/{level}/content-complete` | Operator, unlocked level |
| POST | `/api/my-module/{level}/video-progress` | Operator, content completed first |
| POST | `/api/my-module/{level}/assessment-start` | Operator, content + video completed |
| POST | `/api/my-module/{level}/assessment-submit` | Operator, attempt limit enforced |

Status codes: `401` missing/expired session, `403` role/unit/object violation or `MODULE_LOCKED`, `404` unknown employee/unit/module, `409` prerequisite not met (`CONTENT_REQUIRED`, `VIDEO_REQUIRED`, `ATTEMPT_LIMIT_REACHED`), `429` too many failed logins, `500` server error.

## 6. Dashboard Structure

Corporate Safety Dashboard: 7 KPI cards (Total Employees, Total Units, Overall Completion %, Average Score, On Track, Needs Attention, Inactive), 8 unit performance cards with `[VIEW UNIT]`, unit comparison bar chart, status distribution donut, employee status table with filters, employee detail, level funnel, report builder, audit logs.

Unit Head Dashboard (`{UNIT} - Safety Training Dashboard`): unit KPI cards (Total Employees, Active, Completion %, Average Score, Completed Training, Pending Training, At-Risk, Not Started), employee progress table (ID, Name, Current Level, Progress, Score, Last Activity, Status, Action) with filters (All / Completed / In Progress / Needs Attention / Inactive), at-risk list with reasons, employee detail.

Operator Dashboard: `WELCOME, {NAME}`, profile line (Employee ID, Unit, Role), KPI cards (Current Level, Overall Progress, Completed x/16, Average Score), Production / Safety Learning Roadmap (16 nodes: COMPLETED / CURRENT / LOCKED), Current Module card with `CONTINUE LEARNING`, Training Progress card (Completed / In Progress / Locked / progress bar).

## 7. User Journey For All 3 Roles

Corporate: Login -> Corporate Safety Dashboard -> all 8 unit cards -> `[VIEW UNIT]` -> unit employee table -> employee row -> complete learning progress, roadmap, history, at-risk reasons -> Reports (filter + CSV) -> Activity Logs.

Unit Head: Login -> `{UNIT}` Dashboard -> own unit employees only -> filter by status / search / level -> At-Risk view with reasons -> employee detail -> follow-up. Any attempt to open another unit returns 403.

Operator: Login -> Personal Dashboard -> roadmap shows Level 05 current -> `CONTINUE LEARNING` -> Step 1 content -> mark complete -> Step 2 video -> play to 100% -> Step 3 Start Assessment -> MCQ -> submit -> PASS -> module completed, Level 06 unlocked -> roadmap and progress updated. FAIL -> retake message, module stays incomplete, Level 06 stays locked.

## 8. Learning Progression Logic

```text
CONTENT COMPLETED -> VIDEO COMPLETED -> MCQ SUBMITTED -> REQUIRED PASS SCORE
-> MODULE COMPLETED -> NEXT MODULE UNLOCKED
```

Rules:

1. Level 01 is always the first available level; every other level is `LOCKED` until the previous level is `COMPLETED`.
2. Opening a module never completes it. Each step is a separate server-validated write.
3. Video progress cannot start before content is completed.
4. Assessment cannot start before content and video are completed (`409`).
5. Score >= `assessments.pass_percentage` (80%) -> `COMPLETED`, `completed_at` set, next level row flipped `LOCKED -> CURRENT` in the same transaction, `NEXT_MODULE_UNLOCKED` logged.
6. Score < 80% -> `FAILED`, `completed_at` cleared, next level stays `LOCKED`.
7. Attempt limit (`attempt_limit`, 5) enforced server side -> `409 ATTEMPT_LIMIT_REACHED`.
8. Direct URL/API access to a locked level -> `403 MODULE_LOCKED`, `UNAUTHORIZED_ACCESS_ATTEMPT` logged, no module content in the response body.

## 9. RBAC Implementation Logic

Every request runs the same pipeline:

```text
request
 -> resolve session cookie -> load session row (hash match, not expired)
 -> load user row + role row + unit row from database   (never from the client)
 -> ROLE GUARD   need_role(...)      403 FORBIDDEN
 -> UNIT GUARD   need_unit(...)      403 UNIT_FORBIDDEN   (corporate bypasses; head must match unit_code)
 -> OBJECT GUARD need_employee(...)  403 EMPLOYEE_FORBIDDEN
 -> MODULE GUARD module_guard(...)   403 MODULE_LOCKED
 -> handler
 -> 403 responses are written to activity_logs as UNAUTHORIZED_ACCESS_ATTEMPT
```

Corporate passes the unit guard for every unit; a unit head passes only for `session.unit_code`; operators fail unit and object guards for anything but their own record. Managers cannot call operator learning endpoints (`need_role(..., [OPERATOR])`), and operators cannot call management endpoints.

## 10. UI Page Structure

Shared: login (with demo credential chips), session-expired state, unauthorized state, module-locked state, network/server error state, empty state, profile, logout.

Corporate: Dashboard, Units, Unit Detail, Employees, Learning Progress, Analytics, Reports, Activity Logs, Employee Detail.

Unit Head: Dashboard, My Unit, Employees, Learning Progress, At-Risk Employees, Reports, Profile, Employee Detail.

Operator: Dashboard, My Learning (module flow), Learning Roadmap, My Assessments, My Progress, Profile.

Navigation labels follow Section 18 of the requirement; every navigation item maps to an API route guarded server-side.

## 11. Sample Data Structure

- 8 units: RML, RST, RMU, RMF, SAN, SRS, SVSM, RTL-S, each with a Function Safety Unit Head.
- 1 Corporate Safety Head (`CORP001`).
- Operators across all units with varied states: on track, inactive, at-risk (3 failed attempts), never started, completed.
- 16 modules per unit (128 modules), each with 1 learning content, 1 video, 1 assessment (80% pass, 5 attempts), 3 MCQ questions.
- Seeded `learning_progress` rows for every operator x module (COMPLETED / CURRENT / FAILED / LOCKED) plus `assessment_attempts` history.
- `EMP001` (Kumar, RML) matches the reference sample: 4/16 completed = 25%, average score 82%, current Level 05, Levels 06-16 locked.

All demo passwords: `demo123`.

## 12. Security Considerations

- Passwords: PBKDF2-HMAC-SHA256, 260k iterations, 16-byte random salt, constant-time compare.
- Sessions: 256-bit random token, stored only as SHA-256 hash, 8-hour expiry, server-side delete on logout, `HttpOnly` + `SameSite=Lax` cookie.
- Login throttling: repeated failures per employee ID return `429` and are logged.
- Authorization on every API route (role + unit + object + module guards); frontend role/unit values are never trusted.
- Locked-module responses contain no content, video, or questions.
- Audit logging: LOGIN, LOGOUT, INVALID_LOGIN, MODULE_STARTED, CONTENT_COMPLETED, VIDEO_COMPLETED, ASSESSMENT_STARTED, ASSESSMENT_SUBMITTED, ASSESSMENT_PASSED, ASSESSMENT_FAILED, MODULE_COMPLETED, NEXT_MODULE_UNLOCKED, UNAUTHORIZED_ACCESS_ATTEMPT — with IP and timestamp.
- Response hardening: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`, CSP `default-src 'self'`, `Cache-Control: no-store` on APIs, 256 KB request body limit, path traversal blocked on static files, all error messages generic at 500.

## 13. Development Folder Structure

```text
D:\RML LMS
|-- app.py                    # backend: HTTP server, auth, RBAC, LMS engine, analytics
|-- README.md                 # run instructions + demo credentials
|-- docs/
|   `-- architecture.md       # this design document
|-- static/
|   |-- index.html            # SPA shell
|   |-- styles.css            # enterprise / industrial design system
|   `-- app.js                # role-based SPA: dashboards, roadmap, module flow
|-- tests/
|   `-- test_backend.py       # RBAC, unit isolation, lock bypass, progression tests
|-- data/
|   `-- mill_lms.db           # created and seeded on first run
`-- reference/
    `-- Mill_LMS_Presentation.zip
```

Zero external dependencies: Python 3 standard library only.

## 14. Implementation Phases

1. **Foundation** — schema, seed data, authentication, sessions, RBAC/unit/object guards. (done)
2. **LMS Engine** — 16-level roadmap, module state resolver, lock/unlock enforcement. (done)
3. **Learning Workflow** — content completion, video progress, MCQ scoring, attempt limits, pass/fail. (done)
4. **Dashboards** — corporate analytics, unit dashboard, employee detail, operator dashboard. (done)
5. **Reporting and Hardening** — audit logs, reports with filters and CSV export, at-risk identification, error states, regression tests. (done)
