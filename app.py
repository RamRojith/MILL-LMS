import csv, hashlib, hmac, io, json, os, re, secrets, sqlite3, sys, threading, time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "mill_lms.db"
STATIC_DIR = BASE_DIR / "static"
COOKIE = "mill_lms_session"
UNITS = ["RML", "RST", "RMU", "RMF", "SAN", "SRS", "SVSM", "RTL-S"]
CORP = "corporate_safety_head"
UNIT_HEAD = "function_safety_unit_head"
OPERATOR = "operator_workman"
ROLES = [CORP, UNIT_HEAD, OPERATOR]
PASS_PERCENT = 80
ATTEMPT_LIMIT = 5
TOTAL_LEVELS = 16
INACTIVE_DAYS = 14
PENDING_DAYS = 10
MAX_BODY = 262144
LOGIN_WINDOW = 600
LOGIN_MAX_FAILS = 10

MODULES = [
    "Mill Safety Induction and PPE", "Cotton Handling and Housekeeping", "Machine Guarding Basics",
    "Fire Safety and Emergency Response", "Blow Room Safety and SOP", "Carding Machine Safe Operation",
    "Drawing Frame Process Controls", "Simplex Speed Frame Safety", "Ring Frame Doffing Safety",
    "Winding and Yarn Clearing", "Power and Electrical Isolation", "Chemical and Oil Handling",
    "Quality Defect Prevention", "Incident Reporting and Near Miss", "Maintenance Coordination and LOTO",
    "Final Production Safety Certification",
]
SCORE_CYCLE = [82, 80, 84, 82, 88, 76, 90, 84, 92, 78, 86, 80, 94, 82, 88, 90]
STATUSES = ["ON TRACK", "NEEDS ATTENTION", "INACTIVE", "COMPLETED"]

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS roles(id INTEGER PRIMARY KEY,role_name TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS units(id INTEGER PRIMARY KEY,unit_code TEXT UNIQUE NOT NULL,unit_name TEXT NOT NULL,safety_head_id INTEGER,status TEXT NOT NULL DEFAULT 'ACTIVE',FOREIGN KEY(safety_head_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,employee_id TEXT UNIQUE NOT NULL,name TEXT NOT NULL,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,role_id INTEGER NOT NULL,unit_id INTEGER,status TEXT NOT NULL DEFAULT 'ACTIVE',created_at TEXT NOT NULL,last_login TEXT,FOREIGN KEY(role_id) REFERENCES roles(id),FOREIGN KEY(unit_id) REFERENCES units(id));
CREATE TABLE IF NOT EXISTS modules(id INTEGER PRIMARY KEY,unit_id INTEGER NOT NULL,level_number INTEGER NOT NULL,title TEXT NOT NULL,description TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'ACTIVE',UNIQUE(unit_id,level_number),FOREIGN KEY(unit_id) REFERENCES units(id));
CREATE TABLE IF NOT EXISTS learning_contents(id INTEGER PRIMARY KEY,module_id INTEGER UNIQUE NOT NULL,content TEXT NOT NULL,document_url TEXT,completion_required INTEGER NOT NULL DEFAULT 1,FOREIGN KEY(module_id) REFERENCES modules(id));
CREATE TABLE IF NOT EXISTS videos(id INTEGER PRIMARY KEY,module_id INTEGER UNIQUE NOT NULL,video_url TEXT NOT NULL,duration_seconds INTEGER NOT NULL,completion_required INTEGER NOT NULL DEFAULT 1,FOREIGN KEY(module_id) REFERENCES modules(id));
CREATE TABLE IF NOT EXISTS assessments(id INTEGER PRIMARY KEY,module_id INTEGER UNIQUE NOT NULL,pass_percentage INTEGER NOT NULL,attempt_limit INTEGER,FOREIGN KEY(module_id) REFERENCES modules(id));
CREATE TABLE IF NOT EXISTS questions(id INTEGER PRIMARY KEY,assessment_id INTEGER NOT NULL,question TEXT NOT NULL,option_a TEXT NOT NULL,option_b TEXT NOT NULL,option_c TEXT NOT NULL,option_d TEXT NOT NULL,correct_answer TEXT NOT NULL,FOREIGN KEY(assessment_id) REFERENCES assessments(id));
CREATE TABLE IF NOT EXISTS learning_progress(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL,module_id INTEGER NOT NULL,content_completed INTEGER NOT NULL DEFAULT 0,video_started INTEGER NOT NULL DEFAULT 0,video_progress INTEGER NOT NULL DEFAULT 0,video_completed INTEGER NOT NULL DEFAULT 0,assessment_completed INTEGER NOT NULL DEFAULT 0,score INTEGER,attempts INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'LOCKED',started_at TEXT,completed_at TEXT,last_activity_at TEXT,UNIQUE(user_id,module_id),FOREIGN KEY(user_id) REFERENCES users(id),FOREIGN KEY(module_id) REFERENCES modules(id));
CREATE TABLE IF NOT EXISTS assessment_attempts(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL,module_id INTEGER NOT NULL,attempt_no INTEGER NOT NULL,score INTEGER NOT NULL,passed INTEGER NOT NULL,answers TEXT,created_at TEXT NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id),FOREIGN KEY(module_id) REFERENCES modules(id));
CREATE TABLE IF NOT EXISTS activity_logs(id INTEGER PRIMARY KEY,user_id INTEGER,action TEXT NOT NULL,module_id INTEGER,metadata TEXT,ip_address TEXT,session_id TEXT,timestamp TEXT NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id),FOREIGN KEY(module_id) REFERENCES modules(id));
CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL,session_token_hash TEXT UNIQUE NOT NULL,expires_at TEXT NOT NULL,created_at TEXT NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id));
"""

SEC_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'",
}


class ApiError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


def now():
    return datetime.now(timezone.utc)


def iso(dt=None):
    return (dt or now()).replace(microsecond=0).isoformat()


def parse_time(v):
    try:
        return datetime.fromisoformat(v) if v else None
    except ValueError:
        return None


def db_path():
    return Path(os.environ.get("MILL_LMS_DB", DB_PATH))


@contextmanager
def db():
    c = sqlite3.connect(db_path(), timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
    finally:
        c.close()


def pw_hash(password, salt=None, rounds=260000):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, rounds)
    return f"pbkdf2_sha256${rounds}${salt.hex()}${digest.hex()}"


def pw_ok(password, encoded):
    try:
        _algo, rounds, salt, _digest = encoded.split("$", 3)
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(pw_hash(password, bytes.fromhex(salt), int(rounds)), encoded)


def tok_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------- database

def init_db(force=False):
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if force and path.exists():
        path.unlink()
    with db() as c:
        c.executescript(SCHEMA)
        if c.execute("SELECT COUNT(*) FROM roles").fetchone()[0] == 0:
            seed(c)


def seed(c):
    t = iso()
    roles = {}
    for r in ROLES:
        roles[r] = c.execute("INSERT INTO roles(role_name) VALUES(?)", (r,)).lastrowid
    units = {}
    for code in UNITS:
        name = "RTL-S Safety Unit" if code == "RTL-S" else f"{code} Spinning Unit"
        units[code] = c.execute("INSERT INTO units(unit_code,unit_name,status) VALUES(?,?,'ACTIVE')", (code, name)).lastrowid

    def add_user(emp, name, role, unit=None):
        return c.execute(
            "INSERT INTO users(employee_id,name,username,password_hash,role_id,unit_id,status,created_at) VALUES(?,?,?,?,?,?,'ACTIVE',?)",
            (emp, name, emp.lower(), pw_hash("demo123"), roles[role], units.get(unit), t),
        ).lastrowid

    add_user("CORP001", "Corporate Safety Head", CORP)
    for code in UNITS:
        hid = add_user(f"{code.replace('-', '')}H001", f"{code} Function Safety Head", UNIT_HEAD, code)
        c.execute("UPDATE units SET safety_head_id=? WHERE unit_code=?", (hid, code))

    # employee, name, unit, completed levels, failed attempts on current, days since activity
    operator_defs = [
        ("EMP001", "Kumar", "RML", 4, 0, 1),
        ("EMP002", "Meena", "RML", 2, 0, 16),
        ("EMP003", "Arun", "RML", 16, 0, 1),
        ("EMP004", "Deepa", "RML", 0, 0, 30),
        ("EMP101", "Suresh", "RST", 7, 1, 2),
        ("EMP102", "Lakshmi", "RST", 0, 0, 20),
        ("EMP103", "Ramesh", "RST", 5, 3, 4),
        ("EMP201", "Ravi", "RMU", 3, 0, 1),
        ("EMP202", "Anitha", "RMU", 16, 0, 3),
        ("EMP301", "Naveen", "RMF", 5, 0, 3),
        ("EMP401", "Priya", "SAN", 9, 0, 1),
        ("EMP501", "Bala", "SRS", 6, 3, 5),
        ("EMP601", "Selvi", "SVSM", 1, 0, 6),
        ("EMP701", "Murugan", "RTL-S", 8, 0, 2),
    ]
    operators = [(add_user(emp, name, OPERATOR, code), code, done, fails, days)
                 for emp, name, code, done, fails, days in operator_defs]

    mids = {}
    for code in UNITS:
        for level, title in enumerate(MODULES, 1):
            mid = c.execute(
                "INSERT INTO modules(unit_id,level_number,title,description,status) VALUES(?,?,?,?,'ACTIVE')",
                (units[code], level, f"Level {level:02d} - {title}",
                 f"{code} operator training for {title.lower()} with safety and production controls."),
            ).lastrowid
            mids[(code, level)] = mid
            c.execute("INSERT INTO learning_contents(module_id,content,document_url,completion_required) VALUES(?,?,?,1)",
                      (mid, f"Read the SOP, hazard controls, work instructions, and supervisor checklist for {title}.",
                       f"/documents/{code.lower()}/level-{level:02d}.pdf"))
            c.execute("INSERT INTO videos(module_id,video_url,duration_seconds,completion_required) VALUES(?,?,?,1)",
                      (mid, f"/training-videos/{code.lower()}/level-{level:02d}.mp4", 420 + level * 30))
            aid = c.execute("INSERT INTO assessments(module_id,pass_percentage,attempt_limit) VALUES(?,?,?)",
                            (mid, PASS_PERCENT, ATTEMPT_LIMIT)).lastrowid
            qs = [
                (f"What must be checked before starting Level {level:02d} work?",
                 "PPE and machine condition", "Only production speed", "Shift end report", "Lunch timing", "A"),
                ("When should an unsafe condition be reported?",
                 "After the week ends", "Immediately to the supervisor", "Only after an accident", "Never", "B"),
                ("What does module completion require?",
                 "Opening the screen", "Watching any video", "Content, video, and passing MCQ", "Supervisor rumor", "C"),
            ]
            for q in qs:
                c.execute("INSERT INTO questions(assessment_id,question,option_a,option_b,option_c,option_d,correct_answer) VALUES(?,?,?,?,?,?,?)",
                          (aid, *q))

    for uid, code, done, fails, days in operators:
        last = iso(now() - timedelta(days=days))
        for level in range(1, TOTAL_LEVELS + 1):
            mid = mids[(code, level)]
            if level <= done:
                score = SCORE_CYCLE[(level - 1) % len(SCORE_CYCLE)]
                started = iso(now() - timedelta(days=level + 2))
                c.execute(
                    "INSERT INTO learning_progress(user_id,module_id,content_completed,video_started,video_progress,video_completed,assessment_completed,score,attempts,status,started_at,completed_at,last_activity_at) "
                    "VALUES(?,?,1,1,100,1,1,?,1,'COMPLETED',?,?,?)", (uid, mid, score, started, last, last))
                c.execute("INSERT INTO assessment_attempts(user_id,module_id,attempt_no,score,passed,answers,created_at) VALUES(?,?,1,?,1,?,?)",
                          (uid, mid, score, json.dumps({"1": "A", "2": "B", "3": "C"}), last))
            elif level == done + 1 and done < TOTAL_LEVELS:
                if fails:
                    started = iso(now() - timedelta(days=days + PENDING_DAYS + 2))
                    c.execute(
                        "INSERT INTO learning_progress(user_id,module_id,content_completed,video_started,video_progress,video_completed,assessment_completed,score,attempts,status,started_at,completed_at,last_activity_at) "
                        "VALUES(?,?,1,1,100,1,1,?,?,'FAILED',?,NULL,?)", (uid, mid, 60 + fails * 3, fails, started, last))
                    for a in range(1, fails + 1):
                        c.execute("INSERT INTO assessment_attempts(user_id,module_id,attempt_no,score,passed,answers,created_at) VALUES(?,?,?,?,0,?,?)",
                                  (uid, mid, a, 55 + a * 5, json.dumps({"1": "A", "2": "A", "3": "A"}), last))
                else:
                    c.execute("INSERT INTO learning_progress(user_id,module_id,status,started_at,last_activity_at) VALUES(?,?,'CURRENT',?,?)",
                              (uid, mid, iso(now() - timedelta(days=days)) if done else None, last if days <= INACTIVE_DAYS else None))
            else:
                c.execute("INSERT INTO learning_progress(user_id,module_id,status) VALUES(?,?,'LOCKED')", (uid, mid))
    c.commit()


def log(c, uid, action, mid=None, meta=None, ip=None, session_id=None):
    c.execute("INSERT INTO activity_logs(user_id,action,module_id,metadata,ip_address,session_id,timestamp) VALUES(?,?,?,?,?,?,?)",
              (uid, action, mid, json.dumps(meta or {}), ip, session_id, iso()))


# ---------------------------------------------------------------- identity

def user_row(c, where, params):
    return c.execute(
        "SELECT u.*,r.role_name,un.unit_code,un.unit_name FROM users u "
        "JOIN roles r ON r.id=u.role_id LEFT JOIN units un ON un.id=u.unit_id WHERE " + where, params).fetchone()


def user_by_emp(c, emp):
    return user_row(c, "u.employee_id=?", (emp,))


def user_by_id(c, uid):
    return user_row(c, "u.id=?", (uid,))


def public_user(u):
    return {"id": u["id"], "employee_id": u["employee_id"], "name": u["name"], "role": u["role_name"],
            "unit_code": u["unit_code"], "unit_name": u["unit_name"], "status": u["status"],
            "last_login": u["last_login"]}


LOGIN_FAILS = {}
LOGIN_LOCK = threading.Lock()


def _throttle(emp):
    key = emp.upper()
    with LOGIN_LOCK:
        rec = LOGIN_FAILS.get(key)
        if not rec or time.time() - rec["first"] > LOGIN_WINDOW:
            LOGIN_FAILS[key] = {"first": time.time(), "count": 1}
            return False
        rec["count"] += 1
        return rec["count"] >= LOGIN_MAX_FAILS


def authenticate(emp, password, ip=None):
    emp = (emp or "").strip()
    if not emp or not password:
        raise ApiError(401, "INVALID_LOGIN", "Enter your employee ID and password.")
    locked = _throttle(emp)
    with db() as c:
        u = user_by_emp(c, emp)
        if locked:
            if u:
                log(c, u["id"], "LOGIN_LOCKOUT", meta={"employee_id": emp}, ip=ip)
                c.commit()
            raise ApiError(429, "TOO_MANY_ATTEMPTS", "Too many failed login attempts. Try again later.")
        if not u or u["status"] != "ACTIVE" or not pw_ok(password, u["password_hash"]):
            if u:
                log(c, u["id"], "INVALID_LOGIN", meta={"employee_id": emp}, ip=ip)
            c.commit()
            raise ApiError(401, "INVALID_LOGIN", "Invalid employee ID or password.")
        token = secrets.token_urlsafe(32)
        c.execute("UPDATE users SET last_login=? WHERE id=?", (iso(), u["id"]))
        c.execute("INSERT INTO sessions(user_id,session_token_hash,expires_at,created_at) VALUES(?,?,?,?)",
                  (u["id"], tok_hash(token), iso(now() + timedelta(hours=8)), iso()))
        with LOGIN_LOCK:
            LOGIN_FAILS.pop(emp.upper(), None)
        log(c, u["id"], "LOGIN", meta={"employee_id": emp}, ip=ip)
        c.commit()
        return token, public_user(user_by_id(c, u["id"]))


def session_user(token):
    if not token:
        raise ApiError(401, "AUTH_REQUIRED", "Login required.")
    with db() as c:
        s = c.execute("SELECT * FROM sessions WHERE session_token_hash=?", (tok_hash(token),)).fetchone()
        if not s:
            raise ApiError(401, "SESSION_EXPIRED", "Session expired. Please login again.")
        exp = parse_time(s["expires_at"])
        if not exp or exp < now():
            c.execute("DELETE FROM sessions WHERE id=?", (s["id"],))
            c.commit()
            raise ApiError(401, "SESSION_EXPIRED", "Session expired. Please login again.")
        u = user_by_id(c, s["user_id"])
        if not u or u["status"] != "ACTIVE":
            raise ApiError(401, "AUTH_REQUIRED", "Login required.")
        u = dict(u)
        u["_session_id"] = str(s["id"])
        return u


def optional_user(token):
    try:
        return session_user(token)
    except ApiError:
        return None


def logout(token, ip=None):
    if not token:
        return
    with db() as c:
        s = c.execute("SELECT * FROM sessions WHERE session_token_hash=?", (tok_hash(token),)).fetchone()
        if s:
            log(c, s["user_id"], "LOGOUT", ip=ip)
            c.execute("DELETE FROM sessions WHERE id=?", (s["id"],))
            c.commit()


# ---------------------------------------------------------------- guards

def need_role(u, roles):
    if u["role_name"] not in roles:
        raise ApiError(403, "FORBIDDEN", "You are not authorized to access this resource.")


def need_unit(u, unit):
    if u["role_name"] == CORP:
        return
    if u["role_name"] == UNIT_HEAD and u["unit_code"] == unit:
        return
    raise ApiError(403, "UNIT_FORBIDDEN", "You cannot access another unit's training data.")


def need_employee(actor, target):
    if actor["role_name"] == CORP:
        return
    if actor["role_name"] == UNIT_HEAD and target["role_name"] == OPERATOR and actor["unit_id"] == target["unit_id"]:
        return
    raise ApiError(403, "EMPLOYEE_FORBIDDEN", "You cannot access this employee record.")


def unit_exists(c, code):
    if not c.execute("SELECT 1 FROM units WHERE unit_code=?", (code,)).fetchone():
        raise ApiError(404, "NOT_FOUND", "Unit not found.")


def scope_unit(u, requested=None):
    """Resolve the unit scope of a management request from the session only."""
    if u["role_name"] == CORP:
        return requested or None
    if u["role_name"] == UNIT_HEAD:
        if requested and requested != u["unit_code"]:
            raise ApiError(403, "UNIT_FORBIDDEN", "You cannot access another unit's training data.")
        return u["unit_code"]
    raise ApiError(403, "FORBIDDEN", "You are not authorized to access this resource.")


# ---------------------------------------------------------------- learning queries

def employee_rows(c, unit=None):
    params = [OPERATOR]
    sql = ("SELECT u.*,r.role_name,un.unit_code,un.unit_name FROM users u "
           "JOIN roles r ON r.id=u.role_id LEFT JOIN units un ON un.id=u.unit_id WHERE r.role_name=?")
    if unit:
        sql += " AND un.unit_code=?"
        params.append(unit)
    return c.execute(sql + " ORDER BY un.unit_code,u.employee_id", params).fetchall()


def progress_rows(c, uid):
    return c.execute(
        "SELECT lp.*,m.level_number,m.title,m.description FROM learning_progress lp "
        "JOIN modules m ON m.id=lp.module_id WHERE lp.user_id=? ORDER BY m.level_number", (uid,)).fetchall()


def risks(rows, never_started=False):
    reasons = []
    times = [parse_time(r["last_activity_at"]) for r in rows if r["last_activity_at"]]
    last = max(times) if times else None
    if never_started:
        reasons.append("Training not started")
    elif not last or last < now() - timedelta(days=INACTIVE_DAYS):
        reasons.append(f"No activity for {INACTIVE_DAYS} days")
    failed = [r for r in rows if r["status"] == "FAILED" and r["attempts"] >= 3]
    if failed:
        reasons.append(f"Failed Level {failed[0]['level_number']:02d} assessment {failed[0]['attempts']} times")
    pending = [r for r in rows if r["status"] != "COMPLETED" and r["started_at"]
               and parse_time(r["started_at"]) and parse_time(r["started_at"]) < now() - timedelta(days=PENDING_DAYS)]
    if pending:
        reasons.append(f"Level {pending[0]['level_number']:02d} pending for more than {PENDING_DAYS} days")
    done = len([r for r in rows if r["status"] == "COMPLETED"])
    if done < 2 and last and last < now() - timedelta(days=7):
        reasons.append("Low completion rate")
    return reasons


def summarize(c, u):
    rows = progress_rows(c, u["id"])
    done_rows = [r for r in rows if r["status"] == "COMPLETED"]
    done = len(done_rows)
    scores = [r["score"] for r in rows if r["score"] is not None]
    avg = round(sum(scores) / len(scores)) if scores else 0
    current = min([r["level_number"] for r in rows if r["status"] != "COMPLETED"], default=TOTAL_LEVELS)
    times = [parse_time(r["last_activity_at"]) for r in rows if r["last_activity_at"]]
    last = max(times) if times else None
    never_started = not any(r["content_completed"] or r["video_started"] or r["attempts"] or r["last_activity_at"] for r in rows)
    rr = risks(rows, never_started)
    if done == TOTAL_LEVELS:
        status = "COMPLETED"
    elif never_started or not last or last < now() - timedelta(days=INACTIVE_DAYS):
        status = "INACTIVE"
    elif rr:
        status = "NEEDS ATTENTION"
    else:
        status = "ON TRACK"
    att = c.execute("SELECT COUNT(*) n, COALESCE(SUM(passed=0),0) f FROM assessment_attempts WHERE user_id=?", (u["id"],)).fetchone()
    return {
        "employee_id": u["employee_id"], "name": u["name"], "role": "Operator / Workman",
        "unit_code": u["unit_code"], "unit_name": u["unit_name"], "current_level": current,
        "progress_percent": round(done / TOTAL_LEVELS * 100), "completed_levels": done,
        "in_progress_levels": 0 if done == TOTAL_LEVELS else 1,
        "locked_levels": max(0, TOTAL_LEVELS - done - (0 if done == TOTAL_LEVELS else 1)),
        "average_score": avg, "last_activity": last.isoformat() if last else None,
        "training_status": status, "risk_reasons": rr, "never_started": never_started,
        "total_attempts": att["n"], "failed_assessments": att["f"],
    }


def roadmap(c, u):
    rows = progress_rows(c, u["id"])
    done = {r["level_number"] for r in rows if r["status"] == "COMPLETED"}
    current = min([r["level_number"] for r in rows if r["level_number"] not in done], default=TOTAL_LEVELS)
    out = []
    for r in rows:
        level = r["level_number"]
        state = "COMPLETED" if level in done else "CURRENT" if len(done) < TOTAL_LEVELS and level == current else "LOCKED"
        out.append({
            "module_id": r["module_id"], "level_number": level, "title": r["title"], "state": state,
            "content_completed": bool(r["content_completed"]), "video_progress": r["video_progress"],
            "video_completed": bool(r["video_completed"]), "assessment_completed": bool(r["assessment_completed"]),
            "score": r["score"], "attempts": r["attempts"], "status": r["status"],
        })
    return out


def module_guard(c, u, level, allow_completed=True, ip=None):
    need_role(u, [OPERATOR])
    node = next((x for x in roadmap(c, u) if x["level_number"] == level), None)
    if not node:
        raise ApiError(404, "NOT_FOUND", "Module not found.")
    if node["state"] == "LOCKED" or (node["state"] == "COMPLETED" and not allow_completed):
        log(c, u["id"], "UNAUTHORIZED_ACCESS_ATTEMPT", node["module_id"],
            {"reason": "MODULE_LOCKED", "level": level, "state": node["state"]}, ip=ip)
        c.commit()
        raise ApiError(403, "MODULE_LOCKED", f"Complete Level {level - 1:02d} to unlock Level {level:02d}.")
    m = c.execute("SELECT * FROM modules WHERE id=?", (node["module_id"],)).fetchone()
    p = c.execute("SELECT * FROM learning_progress WHERE user_id=? AND module_id=?", (u["id"], node["module_id"])).fetchone()
    return m, p, node


# ---------------------------------------------------------------- operator learning

def module_detail(u, level, ip=None):
    with db() as c:
        m, p, node = module_guard(c, u, level, ip=ip)
        content = dict(c.execute("SELECT * FROM learning_contents WHERE module_id=?", (m["id"],)).fetchone())
        video = c.execute("SELECT video_url,duration_seconds FROM videos WHERE module_id=?", (m["id"],)).fetchone()
        a = c.execute("SELECT * FROM assessments WHERE module_id=?", (m["id"],)).fetchone()
        qs = c.execute("SELECT id,question,option_a,option_b,option_c,option_d FROM questions WHERE assessment_id=? ORDER BY id",
                       (a["id"],)).fetchall()
        if not p["started_at"]:
            c.execute("UPDATE learning_progress SET started_at=?,last_activity_at=? WHERE id=?", (iso(), iso(), p["id"]))
            log(c, u["id"], "MODULE_STARTED", m["id"], {"level": level}, ip=ip)
        else:
            c.execute("UPDATE learning_progress SET last_activity_at=? WHERE id=?", (iso(), p["id"]))
        c.commit()
        return {"level_number": m["level_number"], "title": m["title"], "description": m["description"],
                "state": node["state"], "unit_code": u["unit_code"], "content": content, "video": dict(video),
                "assessment": {"pass_percentage": a["pass_percentage"], "attempt_limit": a["attempt_limit"],
                               "attempts_used": p["attempts"]},
                "questions": [dict(q) for q in qs], "progress": dict(p)}


def content_done(u, level, ip=None):
    with db() as c:
        m, p, _ = module_guard(c, u, level, False, ip=ip)
        c.execute("UPDATE learning_progress SET content_completed=1,started_at=COALESCE(started_at,?),last_activity_at=? WHERE id=?",
                  (iso(), iso(), p["id"]))
        log(c, u["id"], "CONTENT_COMPLETED", m["id"], {"level": level}, ip=ip, session_id=u.get("_session_id"))
        c.commit()
        return {"ok": True, "message": f"Level {level:02d} learning content completed.", "content_completed": True}


def video_progress(u, level, pct, ip=None):
    pct = max(0, min(100, int(pct)))
    with db() as c:
        m, p, _ = module_guard(c, u, level, False, ip=ip)
        if not p["content_completed"]:
            raise ApiError(409, "CONTENT_REQUIRED", "Complete the learning content before starting the video.")
        completed = 1 if pct >= 100 else 0
        c.execute("UPDATE learning_progress SET video_started=1,video_progress=?,video_completed=?,last_activity_at=? WHERE id=?",
                  (pct, completed, iso(), p["id"]))
        log(c, u["id"], "VIDEO_COMPLETED" if completed else "VIDEO_PROGRESS", m["id"],
            {"level": level, "percent": pct}, ip=ip, session_id=u.get("_session_id"))
        c.commit()
        return {"ok": True, "video_progress": pct, "video_completed": bool(completed)}


def assessment_start(u, level, ip=None):
    with db() as c:
        m, p, _ = module_guard(c, u, level, False, ip=ip)
        if not p["content_completed"]:
            raise ApiError(409, "CONTENT_REQUIRED", "Complete the learning content before taking the assessment.")
        if not p["video_completed"]:
            raise ApiError(409, "VIDEO_REQUIRED", "Complete the training video before taking the assessment.")
        a = c.execute("SELECT * FROM assessments WHERE module_id=?", (m["id"],)).fetchone()
        if a["attempt_limit"] and p["attempts"] >= a["attempt_limit"]:
            raise ApiError(409, "ATTEMPT_LIMIT_REACHED",
                           f"Attempt limit of {a['attempt_limit']} reached. Contact your supervisor.")
        log(c, u["id"], "ASSESSMENT_STARTED", m["id"], {"level": level, "attempt": p["attempts"] + 1},
            ip=ip, session_id=u.get("_session_id"))
        c.commit()
        return {"ok": True, "attempt": p["attempts"] + 1, "pass_percentage": a["pass_percentage"]}


def submit_assessment(u, level, answers, ip=None):
    with db() as c:
        m, p, _ = module_guard(c, u, level, False, ip=ip)
        p = c.execute("SELECT * FROM learning_progress WHERE id=?", (p["id"],)).fetchone()
        if not p["content_completed"]:
            raise ApiError(409, "CONTENT_REQUIRED", "Complete the learning content before taking the assessment.")
        if not p["video_completed"]:
            raise ApiError(409, "VIDEO_REQUIRED", "Complete the training video before taking the assessment.")
        a = c.execute("SELECT * FROM assessments WHERE module_id=?", (m["id"],)).fetchone()
        if a["attempt_limit"] and p["attempts"] >= a["attempt_limit"]:
            log(c, u["id"], "ATTEMPT_LIMIT_REACHED", m["id"], {"level": level, "attempts": p["attempts"]}, ip=ip)
            c.commit()
            raise ApiError(409, "ATTEMPT_LIMIT_REACHED",
                           f"Attempt limit of {a['attempt_limit']} reached for this module. Contact your supervisor.")
        qs = c.execute("SELECT * FROM questions WHERE assessment_id=? ORDER BY id", (a["id"],)).fetchall()
        selected = {}
        correct = 0
        for q in qs:
            ans = str(answers.get(str(q["id"]), answers.get(q["id"], "")) or "").strip().upper()
            selected[str(q["id"])] = ans
            if ans == q["correct_answer"]:
                correct += 1
        score = round(correct / len(qs) * 100) if qs else 0
        attempts = p["attempts"] + 1
        passed = score >= a["pass_percentage"]
        ts = iso()
        c.execute("UPDATE learning_progress SET assessment_completed=1,score=?,attempts=?,status=?,completed_at=?,last_activity_at=? WHERE id=?",
                  (score, attempts, "COMPLETED" if passed else "FAILED", ts if passed else None, ts, p["id"]))
        c.execute("INSERT INTO assessment_attempts(user_id,module_id,attempt_no,score,passed,answers,created_at) VALUES(?,?,?,?,?,?,?)",
                  (u["id"], m["id"], attempts, score, 1 if passed else 0, json.dumps(selected), ts))
        log(c, u["id"], "ASSESSMENT_SUBMITTED", m["id"], {"level": level, "score": score, "attempt": attempts}, ip=ip,
            session_id=u.get("_session_id"))
        log(c, u["id"], "ASSESSMENT_PASSED" if passed else "ASSESSMENT_FAILED", m["id"],
            {"level": level, "score": score}, ip=ip)
        next_unlocked = None
        if passed:
            log(c, u["id"], "MODULE_COMPLETED", m["id"], {"level": level}, ip=ip)
            nm = c.execute("SELECT id,level_number FROM modules WHERE unit_id=? AND level_number=?",
                           (u["unit_id"], level + 1)).fetchone()
            if nm:
                c.execute("UPDATE learning_progress SET status='CURRENT',started_at=COALESCE(started_at,?),last_activity_at=? "
                          "WHERE user_id=? AND module_id=? AND status='LOCKED'", (ts, ts, u["id"], nm["id"]))
                next_unlocked = nm["level_number"]
                log(c, u["id"], "NEXT_MODULE_UNLOCKED", nm["id"], {"level": next_unlocked}, ip=ip)
        c.commit()
        return {"passed": passed, "score": score, "attempts": attempts, "attempt_limit": a["attempt_limit"],
                "pass_percentage": a["pass_percentage"], "next_unlocked": next_unlocked,
                "completed_levels": level if passed else level - 1}


def my_profile(u):
    need_role(u, [OPERATOR])
    with db() as c:
        return {"profile": public_user(u), "summary": summarize(c, u), "roadmap": roadmap(c, u)}


def my_roadmap(u):
    need_role(u, [OPERATOR])
    with db() as c:
        return {"summary": summarize(c, u), "roadmap": roadmap(c, u)}


def my_progress(u):
    need_role(u, [OPERATOR])
    with db() as c:
        rows = progress_rows(c, u["id"])
        modules = [{"level_number": r["level_number"], "title": r["title"], "status": r["status"],
                    "content_completed": bool(r["content_completed"]), "video_progress": r["video_progress"],
                    "video_completed": bool(r["video_completed"]), "score": r["score"], "attempts": r["attempts"],
                    "started_at": r["started_at"], "completed_at": r["completed_at"],
                    "last_activity_at": r["last_activity_at"]} for r in rows]
        return {"profile": public_user(u), "summary": summarize(c, u), "roadmap": roadmap(c, u), "modules": modules}


def my_assessments(u):
    need_role(u, [OPERATOR])
    with db() as c:
        rows = c.execute(
            "SELECT aa.*,m.level_number,m.title,a.pass_percentage FROM assessment_attempts aa "
            "JOIN modules m ON m.id=aa.module_id JOIN assessments a ON a.module_id=m.id "
            "WHERE aa.user_id=? ORDER BY aa.id DESC", (u["id"],)).fetchall()
        history = [{"level_number": r["level_number"], "module": r["title"], "attempt_no": r["attempt_no"],
                    "score": r["score"], "passed": bool(r["passed"]), "pass_percentage": r["pass_percentage"],
                    "status": "PASSED" if r["passed"] else "FAILED", "submitted_at": r["created_at"]} for r in rows]
        p_rows = progress_rows(c, u["id"])
        pending = [{"level_number": r["level_number"], "module": r["title"], "attempts": r["attempts"],
                    "score": r["score"], "status": r["status"]}
                   for r in p_rows if r["status"] in ("CURRENT", "FAILED")]
        return {"summary": summarize(c, u), "history": history, "pending": pending,
                "pass_percentage": PASS_PERCENT, "attempt_limit": ATTEMPT_LIMIT}


# ---------------------------------------------------------------- management analytics

def dash(c, unit=None):
    ss = [summarize(c, r) for r in employee_rows(c, unit)]
    total = len(ss)
    dist = {s: len([x for x in ss if x["training_status"] == s]) for s in STATUSES}
    return {
        "total_employees": total, "total_units": len(UNITS),
        "overall_completion_percent": round(sum(x["progress_percent"] for x in ss) / total) if total else 0,
        "average_score": round(sum(x["average_score"] for x in ss) / total) if total else 0,
        "on_track": dist["ON TRACK"], "needs_attention": dist["NEEDS ATTENTION"],
        "inactive": dist["INACTIVE"], "completed": dist["COMPLETED"],
        "not_started": len([x for x in ss if x["never_started"]]),
        "active_employees": total - dist["INACTIVE"],
        "completed_training": dist["COMPLETED"],
        "pending_training": total - dist["COMPLETED"],
        "at_risk": dist["NEEDS ATTENTION"] + dist["INACTIVE"],
        "status_distribution": dist,
    }


def unit_perf(c):
    out = []
    for code in UNITS:
        row = c.execute("SELECT unit_code,unit_name,status FROM units WHERE unit_code=?", (code,)).fetchone()
        d = dash(c, code)
        head = c.execute("SELECT employee_id,name FROM users WHERE id=(SELECT safety_head_id FROM units WHERE unit_code=?)",
                         (code,)).fetchone()
        out.append({
            "unit_code": code, "unit_name": row["unit_name"] if row else code, "status": row["status"] if row else "ACTIVE",
            "safety_head": {"employee_id": head["employee_id"], "name": head["name"]} if head else None,
            "employee_count": d["total_employees"], "active_employees": d["active_employees"],
            "average_progress": d["overall_completion_percent"], "completion_percent": d["overall_completion_percent"],
            "average_score": d["average_score"], "on_track": d["on_track"], "at_risk": d["at_risk"],
            "inactive": d["inactive"], "not_started": d["not_started"], "status_distribution": d["status_distribution"],
        })
    return out


def level_funnel(c, unit=None):
    rows = c.execute(
        "SELECT m.level_number,lp.status,COUNT(*) n,COALESCE(AVG(lp.score),0) avg_score "
        "FROM modules m JOIN units un ON un.id=m.unit_id "
        "LEFT JOIN users u ON u.unit_id=un.id AND u.role_id=(SELECT id FROM roles WHERE role_name=?) "
        "LEFT JOIN learning_progress lp ON lp.module_id=m.id AND lp.user_id=u.id "
        + ("WHERE un.unit_code=? " if unit else "") +
        "GROUP BY m.level_number,lp.status ORDER BY m.level_number", ([OPERATOR, unit] if unit else [OPERATOR])).fetchall()
    funnel = {}
    for r in rows:
        lvl = funnel.setdefault(r["level_number"], {"level": r["level_number"], "completed": 0, "in_progress": 0,
                                                    "locked": 0, "scores": []})
        if r["status"] == "COMPLETED":
            lvl["completed"] += r["n"]
            if r["avg_score"]:
                lvl["scores"].append(round(r["avg_score"]))
        elif r["status"] in ("CURRENT", "FAILED"):
            lvl["in_progress"] += r["n"]
            if r["avg_score"]:
                lvl["scores"].append(round(r["avg_score"]))
        elif r["status"]:
            lvl["locked"] += r["n"]
    out = []
    for k in sorted(funnel):
        lvl = funnel[k]
        out.append({"level": lvl["level"], "completed": lvl["completed"], "in_progress": lvl["in_progress"],
                    "locked": lvl["locked"], "average_score": round(sum(lvl["scores"]) / len(lvl["scores"])) if lvl["scores"] else 0})
    return out


def summarize_list(c, rows, unit=None):
    return [summarize(c, r) for r in rows]


def filter_employees(c, unit, status=None, q=None, level=None, min_progress=None, max_score=None):
    out = summarize_list(c, employee_rows(c, unit))
    if status:
        out = [x for x in out if x["training_status"] == status.upper()]
    if q:
        needle = q.lower()
        out = [x for x in out if needle in x["employee_id"].lower() or needle in x["name"].lower()]
    if level:
        try:
            out = [x for x in out if x["current_level"] == int(level)]
        except ValueError:
            pass
    if min_progress:
        try:
            out = [x for x in out if x["progress_percent"] >= int(min_progress)]
        except ValueError:
            pass
    if max_score:
        try:
            out = [x for x in out if x["average_score"] <= int(max_score)]
        except ValueError:
            pass
    return out


def at_risk(u, unit=None):
    need_role(u, [CORP, UNIT_HEAD])
    unit = scope_unit(u, unit)
    with db() as c:
        if unit:
            unit_exists(c, unit)
        rows = filter_employees(c, unit)
        out = []
        for r in rows:
            if r["training_status"] in ("NEEDS ATTENTION", "INACTIVE"):
                out.append({**r, "reason": r["risk_reasons"][0] if r["risk_reasons"] else "Needs review"})
        out.sort(key=lambda x: (x["training_status"], x["unit_code"], x["employee_id"]))
        return {"unit": unit, "count": len(out), "employees": out}


def corporate_dashboard(u):
    need_role(u, [CORP])
    with db() as c:
        return {"kpis": dash(c), "units": unit_perf(c),
                "employees": summarize_list(c, employee_rows(c)),
                "generated_at": iso()}


def unit_detail(u, unit):
    need_role(u, [CORP, UNIT_HEAD])
    need_unit(u, unit)
    with db() as c:
        unit_exists(c, unit)
        row = c.execute("SELECT * FROM units WHERE unit_code=?", (unit,)).fetchone()
        head = c.execute("SELECT employee_id,name FROM users WHERE id=(SELECT safety_head_id FROM units WHERE unit_code=?)",
                         (unit,)).fetchone()
        employees = filter_employees(c, unit)
        return {
            "unit": {"unit_code": row["unit_code"], "unit_name": row["unit_name"], "status": row["status"],
                     "safety_head": {"employee_id": head["employee_id"], "name": head["name"]} if head else None},
            "unit_code": unit, "kpis": dash(c, unit), "employees": employees,
            "at_risk": [x for x in employees if x["training_status"] in ("NEEDS ATTENTION", "INACTIVE")],
            "generated_at": iso(),
        }


def unit_progress(u, unit):
    need_role(u, [CORP, UNIT_HEAD])
    need_unit(u, unit)
    with db() as c:
        unit_exists(c, unit)
        return {"unit_code": unit, "funnel": level_funnel(c, unit),
                "employees": filter_employees(c, unit), "kpis": dash(c, unit)}


def list_units(u):
    need_role(u, [CORP])
    with db() as c:
        perf = {x["unit_code"]: x for x in unit_perf(c)}
        rows = c.execute("SELECT unit_code,unit_name,status FROM units ORDER BY id").fetchall()
        return [{**dict(r), **perf[r["unit_code"]]} for r in rows]


def list_employees(u, q):
    need_role(u, [CORP, UNIT_HEAD])
    unit = scope_unit(u, q.get("unit", [None])[0])
    with db() as c:
        if unit:
            unit_exists(c, unit)
        return {"unit": unit,
                "employees": filter_employees(
                    c, unit, status=q.get("status", [None])[0], q=q.get("q", [None])[0],
                    level=q.get("level", [None])[0], min_progress=q.get("min_progress", [None])[0],
                    max_score=q.get("max_score", [None])[0])}


def employee_detail(actor, emp):
    need_role(actor, [CORP, UNIT_HEAD])
    with db() as c:
        t = user_by_emp(c, emp)
        if not t:
            raise ApiError(404, "NOT_FOUND", "Employee not found.")
        need_employee(actor, t)
        rows = progress_rows(c, t["id"])
        history = [{"module": r["title"], "level_number": r["level_number"], "attempts": r["attempts"],
                    "score": r["score"], "status": r["status"], "completed_date": r["completed_at"],
                    "started_at": r["started_at"], "last_activity_at": r["last_activity_at"]} for r in rows
                   if r["status"] in ("COMPLETED", "FAILED", "CURRENT")]
        attempts = c.execute(
            "SELECT aa.*,m.level_number,m.title FROM assessment_attempts aa JOIN modules m ON m.id=aa.module_id "
            "WHERE aa.user_id=? ORDER BY aa.id DESC", (t["id"],)).fetchall()
        logs = c.execute(
            "SELECT al.action,al.metadata,al.timestamp,m.level_number FROM activity_logs al "
            "LEFT JOIN modules m ON m.id=al.module_id WHERE al.user_id=? ORDER BY al.id DESC LIMIT 50", (t["id"],)).fetchall()
        return {
            "profile": public_user(t), "summary": summarize(c, t),
            "roadmap": roadmap(c, t) if t["role_name"] == OPERATOR else [],
            "training_history": history,
            "assessment_attempts": [{"level_number": r["level_number"], "module": r["title"], "attempt_no": r["attempt_no"],
                                     "score": r["score"], "passed": bool(r["passed"]), "submitted_at": r["created_at"]}
                                    for r in attempts],
            "activity": [{"action": r["action"], "metadata": r["metadata"], "timestamp": r["timestamp"],
                          "level_number": r["level_number"]} for r in logs],
        }


def analytics(u):
    need_role(u, [CORP])
    with db() as c:
        units = unit_perf(c)
        all_emp = summarize_list(c, employee_rows(c))
        dist = {s: len([x for x in all_emp if x["training_status"] == s]) for s in STATUSES}
        bands = {"70-79": 0, "80-89": 0, "90-100": 0, "Below 70": 0}
        for x in all_emp:
            s = x["average_score"]
            if s < 70:
                bands["Below 70"] += 1
            elif s < 80:
                bands["70-79"] += 1
            elif s < 90:
                bands["80-89"] += 1
            else:
                bands["90-100"] += 1
        return {"unit_comparison": [{"unit_code": x["unit_code"], "completion_percent": x["completion_percent"],
                                     "average_score": x["average_score"], "employee_count": x["employee_count"]}
                                    for x in units],
                "status_distribution": dist,
                "score_bands": [{"band": k, "count": v} for k, v in bands.items()],
                "level_funnel": level_funnel(c),
                "at_risk": at_risk(u)["employees"],
                "generated_at": iso()}


def build_report(u, q):
    need_role(u, [CORP, UNIT_HEAD])
    unit = scope_unit(u, q.get("unit", [None])[0])
    status = q.get("status", [None])[0]
    level = q.get("level", [None])[0]
    date_from = q.get("from", [None])[0]
    date_to = q.get("to", [None])[0]
    scope = q.get("scope", ["employee"])[0]
    fmt = q.get("format", ["json"])[0]
    search = q.get("q", [None])[0]
    with db() as c:
        if unit:
            unit_exists(c, unit)
        rows = filter_employees(c, unit, status=status, q=search, level=level)

        def in_range(day):
            if not (date_from or date_to):
                return True
            if not day:
                return False
            if date_from and day < date_from:
                return False
            if date_to and day > date_to:
                return False
            return True

        data = []
        if scope == "module":
            header = ["employee_id", "name", "unit", "level", "module", "status", "attempts", "score",
                      "started_at", "completed_at", "last_activity"]
            for emp in rows:
                target = user_by_emp(c, emp["employee_id"])
                for r in progress_rows(c, target["id"]):
                    if level and r["level_number"] != int(level):
                        continue
                    day = (r["completed_at"] or r["last_activity_at"] or "")[:10]
                    if not in_range(day):
                        continue
                    data.append({"employee_id": emp["employee_id"], "name": emp["name"], "unit": emp["unit_code"],
                                 "level": r["level_number"], "module": r["title"], "status": r["status"],
                                 "attempts": r["attempts"], "score": r["score"] if r["score"] is not None else "",
                                 "started_at": r["started_at"] or "", "completed_at": r["completed_at"] or "",
                                 "last_activity": r["last_activity_at"] or ""})
        else:
            header = ["employee_id", "name", "unit", "role", "current_level", "completed_levels",
                      "progress_percent", "average_score", "total_attempts", "failed_assessments",
                      "last_activity", "training_status", "risk_reasons"]
            for emp in rows:
                if not in_range((emp["last_activity"] or "")[:10]):
                    continue
                data.append({"employee_id": emp["employee_id"], "name": emp["name"], "unit": emp["unit_code"],
                             "role": emp["role"], "current_level": emp["current_level"],
                             "completed_levels": emp["completed_levels"], "progress_percent": emp["progress_percent"],
                             "average_score": emp["average_score"], "total_attempts": emp["total_attempts"],
                             "failed_assessments": emp["failed_assessments"],
                             "last_activity": emp["last_activity"] or "", "training_status": emp["training_status"],
                             "risk_reasons": "; ".join(emp["risk_reasons"])})
        summary = {"rows": len(data),
                   "average_progress": round(sum(d.get("progress_percent", 0) for d in data) / len(data)) if data else 0,
                   "average_score": round(sum(d.get("average_score", 0) for d in data) / len(data)) if data else 0,
                   "status_counts": {s: len([d for d in data if d.get("training_status") == s]) for s in STATUSES}}
        return {"filters": {"unit": unit, "status": status, "level": level, "from": date_from, "to": date_to,
                            "scope": scope, "q": search},
                "generated_at": iso(), "summary": summary, "header": header, "rows": data, "format": fmt}


def audit_logs(u, q):
    need_role(u, [CORP])
    limit = min(int(q.get("limit", ["200"][0]) or 200), 500)
    action = q.get("action", [None])[0]
    emp = q.get("employee_id", [None])[0]
    with db() as c:
        sql = ("SELECT al.*,u.employee_id,u.name,m.level_number FROM activity_logs al "
               "LEFT JOIN users u ON u.id=al.user_id LEFT JOIN modules m ON m.id=al.module_id WHERE 1=1")
        params = []
        if action:
            sql += " AND al.action=?"
            params.append(action)
        if emp:
            sql += " AND u.employee_id=?"
            params.append(emp)
        rows = c.execute(sql + " ORDER BY al.id DESC LIMIT ?", (*params, limit)).fetchall()
        actions = [r[0] for r in c.execute("SELECT DISTINCT action FROM activity_logs ORDER BY action").fetchall()]
        return {"logs": [dict(r) for r in rows], "actions": actions}


def health(u=None):
    return {"ok": True, "service": "MILL LMS", "time": iso()}


# ---------------------------------------------------------------- http

def cookie(headers):
    raw = headers.get("Cookie")
    if not raw:
        return None
    jar = SimpleCookie(raw)
    m = jar.get(COOKIE)
    return m.value if m else None


def send_json(h, status, payload, headers=None):
    body = json.dumps(payload, indent=2).encode()
    h.send_response(status)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Cache-Control", "no-store")
    for k, v in SEC_HEADERS.items():
        h.send_header(k, v)
    for k, v in (headers or {}).items():
        h.send_header(k, v)
    h.end_headers()
    h.wfile.write(body)


def send_raw(h, status, body, ctype, headers=None):
    data = body.encode() if isinstance(body, str) else body
    h.send_response(status)
    h.send_header("Content-Type", ctype)
    h.send_header("Content-Length", str(len(data)))
    h.send_header("Cache-Control", "no-store")
    for k, v in SEC_HEADERS.items():
        h.send_header(k, v)
    for k, v in (headers or {}).items():
        h.send_header(k, v)
    h.end_headers()
    h.wfile.write(data)


def to_csv(header, rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow([r.get(k, "") for k in header])
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    server_version = "MillLMS/1.0"

    def handle_api_error(self, e, path=""):
        if isinstance(e, ApiError):
            if e.status == 403 and e.code != "MODULE_LOCKED":
                user = optional_user(cookie(self.headers))
                if user:
                    try:
                        with db() as c:
                            log(c, user["id"], "UNAUTHORIZED_ACCESS_ATTEMPT",
                                meta={"path": path, "code": e.code, "reason": e.message},
                                ip=self.client_address[0], session_id=user.get("_session_id"))
                            c.commit()
                    except Exception:
                        pass
            send_json(self, e.status, {"error": e.code, "message": e.message})
        else:
            send_json(self, 500, {"error": "SERVER_ERROR", "message": "Unexpected server error."})

    def do_GET(self):
        try:
            p = urlparse(self.path)
            if p.path == "/":
                return self.file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            if p.path.startswith("/static/"):
                f = (STATIC_DIR / p.path.replace("/static/", "", 1)).resolve()
                if not str(f).startswith(str(STATIC_DIR.resolve())):
                    raise ApiError(403, "FORBIDDEN", "Invalid static path.")
                ctype = "text/css; charset=utf-8" if f.suffix == ".css" else "application/javascript; charset=utf-8"
                return self.file(f, ctype)
            self.api_get(p)
        except ApiError as e:
            self.handle_api_error(e, self.path)
        except Exception:
            self.handle_api_error(Exception("server"), self.path)

    def do_POST(self):
        try:
            p = urlparse(self.path)
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length > MAX_BODY:
                raise ApiError(413, "PAYLOAD_TOO_LARGE", "Request body too large.")
            raw = self.rfile.read(length).decode() if length else "{}"
            try:
                data = json.loads(raw or "{}")
            except json.JSONDecodeError:
                raise ApiError(400, "BAD_REQUEST", "Invalid JSON body.")
            if p.path == "/api/login":
                token, u = authenticate(data.get("employee_id", ""), data.get("password", ""), self.client_address[0])
                return send_json(self, 200, {"user": u},
                                 {"Set-Cookie": f"{COOKIE}={token}; Path=/; Max-Age=28800; HttpOnly; SameSite=Lax"})
            if p.path == "/api/logout":
                logout(cookie(self.headers), self.client_address[0])
                return send_json(self, 200, {"ok": True},
                                 {"Set-Cookie": f"{COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"})
            u = session_user(cookie(self.headers))
            m = re.fullmatch(r"/api/my-module/(\d+)/(content-complete|video-progress|assessment-start|assessment-submit)",
                             p.path)
            if m:
                level, action = int(m.group(1)), m.group(2)
                ip = self.client_address[0]
                if action == "content-complete":
                    return send_json(self, 200, content_done(u, level, ip))
                if action == "video-progress":
                    return send_json(self, 200, video_progress(u, level, data.get("percent", 100), ip))
                if action == "assessment-start":
                    return send_json(self, 200, assessment_start(u, level, ip))
                return send_json(self, 200, submit_assessment(u, level, data.get("answers", {}), ip))
            raise ApiError(404, "NOT_FOUND", "Endpoint not found.")
        except ApiError as e:
            self.handle_api_error(e, self.path)
        except Exception:
            self.handle_api_error(Exception("server"), self.path)

    def api_get(self, p):
        q = parse_qs(p.query)
        path = p.path
        if path == "/api/health":
            return send_json(self, 200, health())
        u = session_user(cookie(self.headers))
        if path == "/api/me":
            return send_json(self, 200, {"user": public_user(u)})
        if path == "/api/corporate/dashboard":
            return send_json(self, 200, corporate_dashboard(u))
        if path == "/api/analytics":
            return send_json(self, 200, analytics(u))
        if path == "/api/units":
            return send_json(self, 200, {"units": list_units(u)})
        m = re.fullmatch(r"/api/units/([A-Za-z-]+)(/dashboard|/employees|/progress)?", path)
        if m:
            code, sub = m.group(1), m.group(2) or ""
            if sub == "/employees":
                need_role(u, [CORP, UNIT_HEAD])
                need_unit(u, code)
                with db() as c:
                    unit_exists(c, code)
                q2 = {k: v for k, v in q.items() if k != "unit"}
                q2["unit"] = [code]
                return send_json(self, 200, list_employees(u, q2))
            if sub == "/progress":
                return send_json(self, 200, unit_progress(u, code))
            return send_json(self, 200, unit_detail(u, code))
        if path == "/api/unit/dashboard":
            need_role(u, [UNIT_HEAD])
            return send_json(self, 200, unit_detail(u, u["unit_code"]))
        if path == "/api/unit/progress":
            need_role(u, [UNIT_HEAD])
            return send_json(self, 200, unit_progress(u, u["unit_code"]))
        if path == "/api/employees":
            return send_json(self, 200, list_employees(u, q))
        m = re.fullmatch(r"/api/employees/([A-Za-z0-9-]+)", path)
        if m:
            return send_json(self, 200, employee_detail(u, m.group(1)))
        if path == "/api/at-risk":
            return send_json(self, 200, at_risk(u, q.get("unit", [None])[0]))
        if path == "/api/reports":
            report = build_report(u, q)
            if report["format"] == "csv":
                return send_raw(self, 200, to_csv(report["header"], report["rows"]), "text/csv; charset=utf-8",
                                {"Content-Disposition": 'attachment; filename="mill_lms_report.csv"'})
            return send_json(self, 200, report)
        if path == "/api/audit-logs":
            return send_json(self, 200, audit_logs(u, q))
        if path == "/api/my-profile":
            return send_json(self, 200, my_profile(u))
        if path == "/api/my-roadmap":
            return send_json(self, 200, my_roadmap(u))
        if path == "/api/my-progress":
            return send_json(self, 200, my_progress(u))
        if path == "/api/my-assessments":
            return send_json(self, 200, my_assessments(u))
        m = re.fullmatch(r"/api/my-module/(\d+)", path)
        if m:
            return send_json(self, 200, module_detail(u, int(m.group(1)), self.client_address[0]))
        raise ApiError(404, "NOT_FOUND", "Endpoint not found.")

    def file(self, path, ctype):
        if not path.exists() or not path.is_file():
            raise ApiError(404, "NOT_FOUND", "File not found.")
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in SEC_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), fmt % args))


def run(host="127.0.0.1", port=8000):
    init_db()
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"MILL LMS running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run(port=int(os.environ.get("PORT", "8000")))
