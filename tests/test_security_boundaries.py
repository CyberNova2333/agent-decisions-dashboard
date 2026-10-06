"""Security regressions exercise public HTTP routes and persistent state."""
import http.client
import json
import os
import sqlite3
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from http.server import HTTPServer

from core.config import Config
from core.server import DashboardServer, make_handler
from core.decision_service import TopicValidationError


class SecurityBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cfg = Config({"git_commit": {"enabled": False}}, self.root)
        self.app = DashboardServer(self.cfg)
        self.svc = self.app.service
        self.svc.save_topic("a", {"title": "Original", "workflow_state": "decided",
                                  "decision_outcome": "accepted", "new_user_opinion": "Keep history"})
        self.httpd = HTTPServer(("127.0.0.1", 0), make_handler(self.app))
        self.httpd.RequestHandlerClass.log_message = lambda *args: None
        self.worker = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.worker.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.worker.join(5)

    def request(self, path, payload=None, headers=None, method=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_port, timeout=5)
        try:
            hdr = {"Content-Type": "application/json"}
            hdr.update(headers or {})
            conn.request(method or ("POST" if payload is not None else "GET"), path,
                         json.dumps(payload) if payload is not None else None, hdr)
            res = conn.getresponse()
            body = res.read()
            return res.status, json.loads(body) if "application/json" in res.getheader("Content-Type", "") else body
        finally:
            conn.close()

    def state(self):
        return (self.svc.db.get_topic("a"), (self.cfg.decisions_dir / "a.md").read_bytes(),
                self.svc.db.get_revisions(), self.cfg.metadata_json_path.read_bytes())

    def test_dns_rebinding_host_rejected_for_read_write_head_and_options(self):
        before = self.state()
        for method, path, body in [("GET", "/api/topics", None), ("HEAD", "/dashboard.html", None),
                                   ("OPTIONS", "/api/topic/a/save", None),
                                   ("POST", "/api/topic/a/save", {"title": "Injected", "expected_version": 1})]:
            with self.subTest(method=method):
                status, _ = self.request(path, body, {"Host": f"attacker.invalid:{self.httpd.server_port}"}, method)
                self.assertEqual(status, 403)
        self.assertEqual(self.state(), before)

    def test_existing_topic_writes_require_version(self):
        before = self.state()
        for suffix, body in [("save", {"title": "Overwrite"}), ("verify", {"impl_commit": "abc123"}),
                             ("restore", {"rev_id": self.svc.db.get_revisions()[0]["rev_id"]})]:
            with self.subTest(endpoint=suffix):
                status, _ = self.request(f"/api/topic/a/{suffix}", body)
                self.assertEqual(status, 428)
        self.assertEqual(self.state(), before)

    def test_verify_http_honors_stale_version(self):
        self.svc.save_topic("a", {"title": "Winner"}, expected_version=1)
        before = self.state()
        status, _ = self.request("/api/topic/a/verify", {"impl_commit": "abc123", "expected_version": 1})
        self.assertEqual(status, 409)
        self.assertEqual(self.state(), before)

    def test_verify_http_file_failure_does_not_update_database(self):
        before = self.state()
        with patch("core.decision_service.os.replace", side_effect=OSError("injected disk failure")):
            status, _ = self.request("/api/topic/a/verify", {"impl_commit": "abc123", "expected_version": 1})
        self.assertEqual(status, 500)
        self.assertEqual(self.state(), before)

    def test_verify_http_replay_is_one_version_and_one_audit(self):
        payload = {"impl_commit": "abc123", "expected_version": 1}
        first = self.request("/api/topic/a/verify", payload, {"X-Request-ID": "verify-once"})
        before = self.state()
        second = self.request("/api/topic/a/verify", payload, {"X-Request-ID": "verify-once"})
        self.assertEqual(first[0], 200)
        self.assertEqual(second, first)
        self.assertEqual(self.state(), before)
        status, _ = self.request("/api/topic/a/verify", dict(payload, impl_commit="def456"), {"X-Request-ID": "verify-once"})
        self.assertEqual(status, 409)

    def test_verify_missing_authoritative_markdown_rejected(self):
        (self.cfg.decisions_dir / "a.md").unlink()
        before = self.svc.db.get_topic("a")
        with self.assertRaises(TopicValidationError):
            self.app.agent.record_verification("a", "abc123", "QA")
        self.assertEqual(self.svc.db.get_topic("a"), before)

    def test_verify_revision_and_receipt_failures_roll_back_all_state(self):
        for method in ("commit_revision", "record_idempotency"):
            with self.subTest(phase=method):
                before = self.state()
                with patch.object(self.svc.db, method, side_effect=sqlite3.OperationalError("injected")):
                    status, _ = self.request("/api/topic/a/verify", {"impl_commit": "abc123", "expected_version": 1},
                                             {"X-Request-ID": "failed-verify"})
                self.assertEqual(status, 500)
                self.assertEqual(self.state(), before)

    def test_verify_metadata_failure_rolls_back_row_revision_and_receipt(self):
        before = self.state()
        with patch.object(self.svc.recovery, "sync_metadata_json", side_effect=OSError("disk full")):
            status, _ = self.request("/api/topic/a/verify", {"impl_commit": "abc123", "expected_version": 1},
                                     {"X-Request-ID": "export-failure"})
        self.assertEqual(status, 500)
        self.assertEqual(self.state(), before)
        status, _ = self.request("/api/topic/a/verify", {"impl_commit": "abc123", "expected_version": 1},
                                 {"X-Request-ID": "export-failure"})
        self.assertEqual(status, 200)
        self.assertTrue(self.svc.recovery.check_consistency()["consistent"])

    def test_verify_does_not_overwrite_unindexed_metadata_or_history(self):
        path = self.cfg.decisions_dir / "a.md"
        path.write_text(path.read_text(encoding="utf-8").replace("Keep history", "External unsaved edit"), encoding="utf-8")
        before = self.state()
        status, _ = self.request("/api/topic/a/verify", {"impl_commit": "abc123", "expected_version": 1})
        self.assertEqual(status, 400)
        self.assertEqual(self.state(), before)

    def test_partial_body_times_out_without_mutation_and_server_recovers(self):
        before = self.state()
        with patch("core.server.REQUEST_TIMEOUT", 0.15):
            with socket.create_connection(self.httpd.server_address, timeout=3) as client:
                client.sendall((f"POST /api/topic/a/save HTTP/1.1\r\nHost: 127.0.0.1:{self.httpd.server_port}\r\n"
                                "Content-Type: application/json\r\nContent-Length: 100\r\n\r\n{").encode())
                response = http.client.HTTPResponse(client)
                response.begin()
                self.assertEqual(response.status, 408)
                response.read()
        self.assertEqual(self.state(), before)
        self.assertEqual(self.request("/api/topics")[0], 200)

    def test_static_symlink_escape_and_directory_listing_are_blocked(self):
        self.app.web_dir = self.root / "web"
        self.app.web_dir.mkdir()
        (self.app.web_dir / "private").mkdir()
        self.assertEqual(self.request("/private/")[0], 404)
        secret = self.root / "private.txt"
        secret.write_text("not a web asset", encoding="utf-8")
        try:
            os.symlink(secret, self.app.web_dir / "public.txt")
        except OSError:
            self.skipTest("Host does not permit symlink creation")
        self.assertEqual(self.request("/public.txt")[0], 404)

    def test_wrong_scheme_and_port_origins_are_rejected(self):
        for origin in (f"https://127.0.0.1:{self.httpd.server_port}", "http://127.0.0.1:1", "null",
                       f"http://127.0.0.2:{self.httpd.server_port}", f"http://localhost:{self.httpd.server_port}"):
            with self.subTest(origin=origin):
                self.assertEqual(self.request("/api/topics", headers={"Origin": origin})[0], 403)

    def test_new_topic_save_replay_does_not_require_new_version(self):
        payload = {"title": "Created once", "request_id": "create-via-save"}
        first = self.request("/api/topic/new/save", payload)
        self.assertEqual(first[0], 200)
        second = self.request("/api/topic/new/save", payload)
        self.assertEqual(second[0], 200)
        self.assertEqual(first[1]["new_version"], second[1]["new_version"])
        self.assertEqual(len(self.svc.parser.parse_markdown_file(self.cfg.decisions_dir / "new.md")["rounds"]), 0)

    def test_deleted_topic_can_be_restored_but_second_new_write_requires_version(self):
        history = self.svc.db.get_revisions()
        saved_revision = history[0]["rev_id"]
        self.svc.rollback_full(history[-1]["rev_id"])
        self.assertIsNone(self.svc.db.get_topic("a"))
        self.assertEqual(self.request("/api/topic/a/restore", {"rev_id": saved_revision})[0], 200)
        self.assertEqual(self.request("/api/topic/a/restore", {"rev_id": saved_revision})[0], 428)

    def test_full_rollback_requires_current_revision_and_rejects_stale_history(self):
        _, history = self.request("/api/git/log")
        target = history["current_revision"]
        self.svc.save_topic("a", {"title": "Later edit"}, expected_version=1)
        before = self.state()
        self.assertEqual(self.request("/api/rollback", {"rev_id": target})[0], 428)
        self.assertEqual(self.request("/api/rollback", {"rev_id": target, "expected_revision": target})[0], 409)
        self.assertEqual(self.state(), before)
        _, history = self.request("/api/git/log")
        self.assertEqual(self.request("/api/rollback", {"rev_id": target, "expected_revision": history["current_revision"]})[0], 200)
        self.assertEqual(self.svc.db.get_topic("a")["title"], "Original")

    def test_malformed_topic_fields_fail_before_mutation(self):
        before = self.state()
        for field, value in (("title", []), ("content_override", {}), ("decision_outcome", [])):
            with self.subTest(field=field):
                status, _ = self.request("/api/topic/a/save", {field: value, "expected_version": 1})
                self.assertEqual(status, 400)
        self.assertEqual(self.state(), before)

    def test_trusted_static_assets_and_same_origin_writes_still_work(self):
        status, _ = self.request("/dashboard.html")
        self.assertEqual(status, 200)
        status, result = self.request("/api/topic/a/save", {"title": "Updated", "expected_version": 1},
                                      {"Origin": f"http://127.0.0.1:{self.httpd.server_port}"})
        self.assertEqual(status, 200)
        self.assertEqual(result["new_version"], 2)

    def test_non_loopback_listener_rejected_before_storage_initialization(self):
        for host in ("0.0.0.0", "::", "192.168.1.1", "example.org"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                DashboardServer(self.cfg, host=host)

    def test_non_json_cross_site_request_rejected(self):
        before = self.state()
        status, _ = self.request("/api/topic/a/save", {"title": "Injected", "expected_version": 1},
                                 {"Content-Type": "text/plain", "Sec-Fetch-Site": "cross-site"})
        self.assertIn(status, (403, 415))
        self.assertEqual(self.state(), before)

    def test_versions_are_positive_integers_not_booleans_or_floats(self):
        before = self.state()
        for version in (True, 1.5, [], {}, 0):
            with self.subTest(version=version):
                status, _ = self.request("/api/topic/a/save", {"title": "Invalid", "expected_version": version})
                self.assertEqual(status, 400)
        self.assertEqual(self.state(), before)

    def test_explicit_accepted_outcome_overrides_legacy_rejection_text(self):
        self.svc.save_topic("a", {"title": "Accepted", "workflow_state": "decided",
                                  "decision_outcome": "accepted", "decision_status": "已定，非否决"}, expected_version=1)
        ctx = self.app.agent.query_context()
        self.assertEqual([t["id"] for t in ctx["active_decisions"]], ["a"])
        self.assertEqual(ctx["rejected_proposals"], [])

    def test_rejected_topics_can_be_excluded_from_context(self):
        self.svc.save_topic("a", {"title": "Rejected", "workflow_state": "decided",
                                  "decision_outcome": "rejected", "rejection_reason": "No"}, expected_version=1)
        self.assertEqual(self.app.agent.query_context(include_rejected=False)["rejected_proposals"], [])


if __name__ == "__main__":
    unittest.main()
