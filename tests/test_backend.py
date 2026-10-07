"""Regression tests for MILL LMS backend security and learning progression.

Run:  python -m unittest discover -s tests -v
"""
import http.cookiejar
import importlib.util
import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(tempfile.gettempdir(), "mill_lms_test.db")
os.environ["MILL_LMS_DB"] = DB_FILE

_spec = importlib.util.spec_from_file_location("mill_lms_app", os.path.join(ROOT, "app.py"))
app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(app)
app.Handler.log_message = lambda *args, **kwargs: None

SERVER = None
BASE = ""


def setUpModule():
    global SERVER, BASE
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
    app.init_db(force=True)
    SERVER = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    BASE = f"http://127.0.0.1:{SERVER.server_address[1]}"
    threading.Thread(target=SERVER.serve_forever, daemon=True).start()


def tearDownModule():
    if SERVER:
        SERVER.shutdown()
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)


class Client:
    def __init__(self):
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def request(self, path, data=None, method=None, raw=False):
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(BASE + path, data=body, method=method or ("POST" if body else "GET"))
        if body is not None:
            req.add_header("Content-Type", "application/json")
        try:
            resp = self.opener.open(req, timeout=15)
            payload = resp.read().decode()
            status, headers = resp.status, dict(resp.headers)
        except urllib.error.HTTPError as e:
            payload = e.read().decode()
            status, headers = e.code, dict(e.headers)
        if raw:
            return status, payload, headers
        try:
            return status, json.loads(payload or "{}"), headers
        except json.JSONDecodeError:
            return status, payload, headers

    def login(self, employee_id, password="demo123"):
        return self.request("/api/login", {"employee_id": employee_id, "password": password})

    def logout(self):
        return self.request("/api/logout", {})


def correct_answers(questions):
    order = ["A", "B", "C"]
    return {str(q["id"]): order[i % len(order)] for i, q in enumerate(questions)}


def wrong_answers(questions):
    return {str(q["id"]): "D" for q in questions}


class AuthenticationTests(unittest.TestCase):
    def test_login_and_me(self):
        c = Client()
        status, data, headers = c.login("EMP001")
        self.assertEqual(status, 200)
        self.assertEqual(data["user"]["employee_id"], "EMP001")
        self.assertEqual(data["user"]["role"], "operator_workman")
        self.assertIn("HttpOnly", headers.get("Set-Cookie", ""))
        status, data, _ = c.request("/api/me")
        self.assertEqual(status, 200)
        self.assertEqual(data["user"]["unit_code"], "RML")

    def test_invalid_login_rejected(self):
        c = Client()
        status, data, _ = c.login("EMP001", "nope")
        self.assertEqual(status, 401)
        self.assertEqual(data["error"], "INVALID_LOGIN")
        status, data, _ = c.login("UNKNOWN001")
        self.assertEqual(status, 401)

    def test_login_throttled_after_repeated_failures(self):
        c = Client()
        codes = [c.login("THROTTLE01", "bad")[0] for _ in range(12)]
        self.assertIn(429, codes)

    def test_logout_invalidates_session(self):
        c = Client()
        c.login("EMP001")
        self.assertEqual(c.request("/api/me")[0], 200)
        c.logout()
        status, data, _ = c.request("/api/me")
        self.assertEqual(status, 401)
        self.assertIn(data["error"], ("SESSION_EXPIRED", "AUTH_REQUIRED"))

    def test_no_session_returns_401(self):
        c = Client()
        status, data, _ = c.request("/api/my-profile")
        self.assertEqual(status, 401)

    def test_security_headers_present(self):
        c = Client()
        status, body, headers = c.request("/api/health", raw=True)
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(headers.get("X-Frame-Options"), "DENY")


class CorporateAccessTests(unittest.TestCase):
    def setUp(self):
        self.c = Client()
        self.c.login("CORP001")

    def test_dashboard_covers_all_eight_units(self):
        status, data, _ = self.c.request("/api/corporate/dashboard")
        self.assertEqual(status, 200)
        self.assertEqual(len(data["units"]), 8)
        self.assertEqual([u["unit_code"] for u in data["units"]],
                         ["RML", "RST", "RMU", "RMF", "SAN", "SRS", "SVSM", "RTL-S"])
        self.assertIn("total_employees", data["kpis"])
        self.assertIn("status_distribution", data["kpis"])

    def test_units_master_and_detail(self):
        status, data, _ = self.c.request("/api/units")
        self.assertEqual(status, 200)
        self.assertEqual(len(data["units"]), 8)
        self.assertTrue(all(u["safety_head"] for u in data["units"]))
        status, data, _ = self.c.request("/api/units/RML")
        self.assertEqual(status, 200)
        self.assertEqual(data["unit"]["unit_code"], "RML")
        self.assertGreater(data["kpis"]["total_employees"], 0)

    def test_unknown_unit_returns_404(self):
        status, data, _ = self.c.request("/api/units/NOPE/dashboard")
        self.assertEqual(status, 404)

    def test_analytics_and_audit_logs(self):
        status, data, _ = self.c.request("/api/analytics")
        self.assertEqual(status, 200)
        self.assertEqual(len(data["level_funnel"]), 16)
        self.assertIn("status_distribution", data)
        status, data, _ = self.c.request("/api/audit-logs")
        self.assertEqual(status, 200)
        self.assertIsInstance(data["logs"], list)

    def test_employee_detail_any_unit(self):
        status, data, _ = self.c.request("/api/employees/EMP001")
        self.assertEqual(status, 200)
        self.assertEqual(len(data["roadmap"]), 16)
        self.assertIn("training_history", data)
        self.assertIn("assessment_attempts", data)

    def test_unknown_employee_returns_404(self):
        self.assertEqual(self.c.request("/api/employees/EMP999")[0], 404)


class UnitHeadAccessTests(unittest.TestCase):
    def setUp(self):
        self.head = Client()
        self.head.login("RMLH001")

    def test_own_unit_dashboard(self):
        status, data, _ = self.head.request("/api/unit/dashboard")
        self.assertEqual(status, 200)
        self.assertEqual(data["unit"]["unit_code"], "RML")

    def test_other_unit_urls_are_denied(self):
        for path in ["/api/units/RST", "/api/units/RST/dashboard", "/api/units/RST/employees",
                     "/api/units/RST/progress", "/api/units/RMU/dashboard", "/api/units/RTL-S/employees"]:
            status, data, _ = self.head.request(path)
            self.assertEqual(status, 403, path)
            self.assertEqual(data["error"], "UNIT_FORBIDDEN", path)

    def test_other_unit_query_param_denied(self):
        for path in ["/api/employees?unit=RST", "/api/reports?unit=RST", "/api/at-risk?unit=RST"]:
            status, data, _ = self.head.request(path)
            self.assertEqual(status, 403, path)
            self.assertEqual(data["error"], "UNIT_FORBIDDEN", path)

    def test_employee_list_scoped_to_own_unit(self):
        status, data, _ = self.head.request("/api/employees")
        self.assertEqual(status, 200)
        self.assertTrue(data["employees"])
        self.assertTrue(all(e["unit_code"] == "RML" for e in data["employees"]))

    def test_unit_head_cannot_reach_corporate_endpoints(self):
        for path in ["/api/corporate/dashboard", "/api/analytics", "/api/units", "/api/audit-logs"]:
            status, data, _ = self.head.request(path)
            self.assertEqual(status, 403, path)
            self.assertEqual(data["error"], "FORBIDDEN", path)

    def test_object_level_access_denied_across_units(self):
        status, data, _ = self.head.request("/api/employees/EMP101")
        self.assertEqual(status, 403)
        self.assertEqual(data["error"], "EMPLOYEE_FORBIDDEN")
        status, data, _ = self.head.request("/api/employees/EMP001")
        self.assertEqual(status, 200)
        self.assertEqual(data["profile"]["unit_code"], "RML")

    def test_operator_learning_endpoints_denied(self):
        for path in ["/api/my-profile", "/api/my-roadmap", "/api/my-progress", "/api/my-assessments",
                     "/api/my-module/1"]:
            status, data, _ = self.head.request(path)
            self.assertEqual(status, 403, path)

    def test_reports_scoped_to_own_unit(self):
        status, data, _ = self.head.request("/api/reports")
        self.assertEqual(status, 200)
        self.assertTrue(data["rows"])
        self.assertTrue(all(r["unit"] == "RML" for r in data["rows"]))


class OperatorAccessTests(unittest.TestCase):
    def setUp(self):
        self.op = Client()
        self.op.login("EMP001")

    def test_profile_and_roadmap_states(self):
        status, data, _ = self.op.request("/api/my-profile")
        self.assertEqual(status, 200)
        s = data["summary"]
        self.assertEqual(s["progress_percent"], 25)
        self.assertEqual(s["completed_levels"], 4)
        self.assertEqual(s["average_score"], 82)
        self.assertEqual(s["current_level"], 5)
        states = [n["state"] for n in data["roadmap"]]
        self.assertEqual(states, ["COMPLETED"] * 4 + ["CURRENT"] + ["LOCKED"] * 11)

    def test_management_endpoints_denied(self):
        for path in ["/api/employees", "/api/employees/EMP002", "/api/corporate/dashboard",
                     "/api/units", "/api/units/RML", "/api/units/RML/employees", "/api/unit/dashboard",
                     "/api/analytics", "/api/audit-logs", "/api/reports", "/api/at-risk"]:
            status, data, _ = self.op.request(path)
            self.assertEqual(status, 403, path)

    def test_locked_module_denied_without_content_leak(self):
        for level in (6, 16):
            status, body, _ = self.op.request(f"/api/my-module/{level}", raw=True)
            self.assertEqual(status, 403, f"level {level}")
            payload = json.loads(body)
            self.assertEqual(payload["error"], "MODULE_LOCKED")
            self.assertNotIn("content", payload)
            self.assertNotIn("questions", payload)
            self.assertIn("unlock", payload["message"])
            if level == 6:
                self.assertIn("Level 05", payload["message"])

    def test_locked_module_writes_rejected(self):
        status, data, _ = self.op.request("/api/my-module/6/content-complete", {})
        self.assertEqual(status, 403)
        self.assertEqual(data["error"], "MODULE_LOCKED")
        status, data, _ = self.op.request("/api/my-module/6/assessment-submit", {"answers": {}})
        self.assertEqual(status, 403)

    def test_current_module_details(self):
        status, data, _ = self.op.request("/api/my-module/5")
        self.assertEqual(status, 200)
        self.assertEqual(data["level_number"], 5)
        self.assertEqual(data["state"], "CURRENT")
        self.assertEqual(len(data["questions"]), 3)
        self.assertNotIn("correct_answer", json.dumps(data["questions"]))

    def test_assessment_requires_content_and_video(self):
        status, data, _ = self.op.request("/api/my-module/5/assessment-start", {})
        self.assertEqual(status, 409)
        self.assertEqual(data["error"], "CONTENT_REQUIRED")
        status, data, _ = self.op.request("/api/my-module/5/video-progress", {"percent": 100})
        self.assertEqual(status, 409)
        self.assertEqual(data["error"], "CONTENT_REQUIRED")

    def test_locked_access_is_audited(self):
        self.op.request("/api/my-module/9")
        corp = Client()
        corp.login("CORP001")
        status, data, _ = corp.request("/api/audit-logs?action=UNAUTHORIZED_ACCESS_ATTEMPT")
        self.assertEqual(status, 200)
        self.assertTrue(any("MODULE_LOCKED" in (l.get("metadata") or "") for l in data["logs"]))


class ProgressionTests(unittest.TestCase):
    """EMP201 (RMU) sits on Level 04 with a clean slate."""

    def setUp(self):
        self.op = Client()
        self.op.login("EMP201")

    def test_content_video_assessment_unlock_flow(self):
        status, module, _ = self.op.request("/api/my-module/4")
        self.assertEqual(status, 200)
        self.assertEqual(module["state"], "CURRENT")

        self.assertEqual(self.op.request("/api/my-module/4/content-complete", {})[0], 200)
        status, data, _ = self.op.request("/api/my-module/4/video-progress", {"percent": 40})
        self.assertFalse(data["video_completed"])
        self.assertEqual(self.op.request("/api/my-module/5")[0], 403)

        self.assertEqual(self.op.request("/api/my-module/4/video-progress", {"percent": 100})[0], 200)
        status, data, _ = self.op.request("/api/my-module/4/assessment-start", {})
        self.assertEqual(status, 200)
        self.assertEqual(data["attempt"], 1)

        status, result, _ = self.op.request("/api/my-module/4/assessment-submit",
                                            {"answers": wrong_answers(module["questions"])})
        self.assertEqual(status, 200)
        self.assertFalse(result["passed"])
        self.assertEqual(result["next_unlocked"], None)
        self.assertEqual(self.op.request("/api/my-module/5")[0], 403, "failed assessment must not unlock")

        status, module, _ = self.op.request("/api/my-module/4")
        status, result, _ = self.op.request("/api/my-module/4/assessment-submit",
                                            {"answers": correct_answers(module["questions"])})
        self.assertEqual(status, 200)
        self.assertTrue(result["passed"])
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["next_unlocked"], 5)

        status, next_module, _ = self.op.request("/api/my-module/5")
        self.assertEqual(status, 200)
        self.assertEqual(next_module["state"], "CURRENT")

        status, profile, _ = self.op.request("/api/my-profile")
        self.assertEqual(profile["summary"]["completed_levels"], 4)
        self.assertEqual(profile["summary"]["progress_percent"], 25)
        states = [n["state"] for n in profile["roadmap"]]
        self.assertEqual(states[:5], ["COMPLETED"] * 4 + ["CURRENT"])

    def test_audit_trail_for_learning_events(self):
        self.op.request("/api/my-module/4/content-complete", {})
        corp = Client()
        corp.login("CORP001")
        status, data, _ = corp.request("/api/audit-logs?employee_id=EMP201")
        self.assertEqual(status, 200)
        actions = {l["action"] for l in data["logs"]}
        self.assertIn("CONTENT_COMPLETED", actions)
        self.assertIn("LOGIN", actions)


class AssessmentRulesTests(unittest.TestCase):
    def test_attempt_limit_enforced(self):
        op = Client()
        op.login("EMP101")
        status, module, _ = op.request("/api/my-module/8")
        self.assertEqual(status, 200)
        for _ in range(4):
            status, result, _ = op.request("/api/my-module/8/assessment-submit",
                                           {"answers": wrong_answers(module["questions"])})
            self.assertEqual(status, 200)
            self.assertFalse(result["passed"])
        status, data, _ = op.request("/api/my-module/8/assessment-submit",
                                     {"answers": wrong_answers(module["questions"])})
        self.assertEqual(status, 409)
        self.assertEqual(data["error"], "ATTEMPT_LIMIT_REACHED")
        status, data, _ = op.request("/api/my-module/8/assessment-start", {})
        self.assertEqual(status, 409)

    def test_video_requires_content_then_assessment_requires_video(self):
        op = Client()
        op.login("EMP301")
        self.assertEqual(op.request("/api/my-module/6/content-complete", {})[0], 200)
        status, data, _ = op.request("/api/my-module/6/video-progress", {"percent": 100})
        self.assertEqual(status, 200)
        self.assertTrue(data["video_completed"])
        status, data, _ = op.request("/api/my-module/6/assessment-start", {})
        self.assertEqual(status, 200)


class ReportAndFilterTests(unittest.TestCase):
    def setUp(self):
        self.corp = Client()
        self.corp.login("CORP001")

    def test_employee_filters(self):
        status, data, _ = self.corp.request("/api/employees?unit=RML")
        self.assertEqual(status, 200)
        self.assertTrue(all(e["unit_code"] == "RML" for e in data["employees"]))
        status, data, _ = self.corp.request("/api/employees?status=COMPLETED")
        self.assertTrue(all(e["training_status"] == "COMPLETED" for e in data["employees"]))
        status, data, _ = self.corp.request("/api/employees?q=EMP001")
        self.assertEqual([e["employee_id"] for e in data["employees"]], ["EMP001"])

    def test_at_risk_identification(self):
        status, data, _ = self.corp.request("/api/at-risk")
        self.assertEqual(status, 200)
        ids = {e["employee_id"] for e in data["employees"]}
        self.assertIn("EMP002", ids, "employee with no activity for 14+ days")
        for e in data["employees"]:
            self.assertIn(e["training_status"], ("NEEDS ATTENTION", "INACTIVE"))
            self.assertTrue(e["reason"])

    def test_report_json_and_csv(self):
        status, data, _ = self.corp.request("/api/reports")
        self.assertEqual(status, 200)
        self.assertEqual(data["summary"]["rows"], len(data["rows"]))
        self.assertTrue(any(r["unit"] == "RTL-S" for r in data["rows"]))
        status, data, _ = self.corp.request("/api/reports?scope=module&unit=RML")
        self.assertTrue(data["rows"])
        self.assertTrue(all(r["unit"] == "RML" for r in data["rows"]))
        self.assertIn("level", data["header"])
        status, body, headers = self.corp.request("/api/reports?format=csv", raw=True)
        self.assertEqual(status, 200)
        self.assertIn("text/csv", headers.get("Content-Type", ""))
        self.assertIn("attachment", headers.get("Content-Disposition", ""))
        self.assertEqual(body.splitlines()[0].split(",")[0], "employee_id")

    def test_unit_detail_and_funnel(self):
        status, data, _ = self.corp.request("/api/units/RST/progress")
        self.assertEqual(status, 200)
        self.assertEqual(len(data["funnel"]), 16)
        status, data, _ = self.corp.request("/api/units/RST/employees?status=INACTIVE")
        self.assertEqual(status, 200)
        self.assertTrue(all(e["unit_code"] == "RST" for e in data["employees"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
