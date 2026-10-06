"""Integration regressions for retries, legacy data and bounded read costs."""
import http.client
import json
import socket
import sqlite3
import tempfile
import sys
import threading
import unittest
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from core.config import Config
from core.decision_service import DecisionService, TopicValidationError
from core.server import DashboardServer, DashboardHTTPServer, make_handler
from core.git_engine import GitCommitResult
from core.decision_service import IdempotencyConflictError
from core.db import DatabaseManager


class FinalAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cfg = Config({"git_commit": {"enabled": False}}, self.root)
        self.app = DashboardServer(self.cfg)
        self.svc = self.app.service

    def test_legacy_chinese_state_survives_rebuild_then_save(self):
        self.cfg.decisions_dir.mkdir(exist_ok=True)
        (self.cfg.decisions_dir / "old.md").write_text(
            "# Old\n\n> **生命周期**：`🟢 已决策` | **决策状态**：`已定` | **实现现状**：`已实现`\n\n"
            "## 核心论述与现实依据\n\nKeep requirement\n\n## 历史讨论与决策记录\n", encoding="utf-8")
        self.svc.recovery.rebuild_index_from_markdown()
        self.svc.save_topic("old", {"new_user_opinion": "Continue"}, expected_version=1)
        self.assertEqual(self.svc.db.get_topic("old")["implementation_state"], "implemented")
        self.assertTrue(self.svc.recovery.check_consistency()["consistent"])

    def test_old_database_migration_preserves_decision_and_implementation(self):
        path = self.root / "legacy.db"
        with closing(sqlite3.connect(path)) as conn:
            with conn:
                conn.execute("CREATE TABLE topics (id TEXT PRIMARY KEY, title TEXT, lifecycle_status TEXT, impl_status TEXT)")
                conn.execute("INSERT INTO topics VALUES ('legacy', 'Existing decision', 'decided', '已实现')")
        row = DatabaseManager(path).get_topic("legacy")
        self.assertEqual(row["workflow_state"], "decided")
        self.assertEqual(row["implementation_state"], "implemented")

    def test_retry_cannot_report_success_while_export_still_fails(self):
        with patch.object(self.svc.recovery, "sync_metadata_json", side_effect=OSError("disk full")):
            for attempt in range(2):
                with self.subTest(attempt=attempt), self.assertRaises(OSError):
                    self.svc.create_topic({"id": "a", "title": "Keep me"}, request_id="once")
        result = self.svc.create_topic({"id": "a", "title": "Keep me"}, request_id="once")
        self.assertEqual(result["new_version"], 1)
        self.assertEqual(result["export_status"], "ok")
        self.assertEqual(result["git_status"], "disabled")

    def test_retry_never_commits_newer_content_under_an_old_message(self):
        self.svc.save_topic("a", {"title": "Original"})
        payload = {"title": "Interrupted old decision"}
        with patch.object(self.svc.recovery, "sync_metadata_json", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.svc.save_topic("a", payload, expected_version=1, request_id="old")
        self.svc.save_topic("a", {"title": "Newer decision"}, expected_version=2)
        self.cfg._data["git_commit"]["enabled"] = True
        with patch.object(self.svc.git, "commit_decision", return_value=GitCommitResult(True, "committed")) as commit:
            result = self.svc.save_topic("a", payload, expected_version=1, request_id="old")
            commit.assert_not_called()
        self.assertEqual(result["git_status"], "skipped_superseded")
        self.assertEqual(self.svc.db.get_topic("a")["title"], "Newer decision")

    def test_restore_retry_does_not_commit_later_content(self):
        self.svc.save_topic("a", {"title": "First"})
        rev = self.svc.db.get_revisions()[0]["rev_id"]
        self.svc.save_topic("a", {"title": "Second"}, expected_version=1)
        with patch.object(self.svc.recovery, "sync_metadata_json", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.svc.restore_single_topic("a", rev, expected_version=2, request_id="restore")
        self.svc.save_topic("a", {"title": "Later"}, expected_version=3)
        self.cfg._data["git_commit"]["enabled"] = True
        with patch.object(self.svc.git, "commit_decision", return_value=GitCommitResult(True, "committed")) as commit:
            result = self.svc.restore_single_topic("a", rev, expected_version=2, request_id="restore")
            commit.assert_not_called()
        self.assertEqual(result["git_status"], "skipped_superseded")

    def test_restore_request_id_binds_original_version_and_reason(self):
        self.svc.save_topic("a", {"title": "First"})
        rev = self.svc.db.get_revisions()[0]["rev_id"]
        self.svc.save_topic("a", {"title": "Second"}, expected_version=1)
        self.svc.restore_single_topic("a", rev, expected_version=2, request_id="restore", reason="Original reason")
        with self.assertRaises(IdempotencyConflictError):
            self.svc.restore_single_topic("a", rev, expected_version=3, request_id="restore", reason="Different reason")

    def test_restore_rejects_ambiguous_old_snapshot_before_any_writes(self):
        self.svc.save_topic("a", {"title": "Current", "new_user_opinion": "Keep this"})
        rev = self.svc.db.get_revisions()[0]["rev_id"]
        snapshot = json.loads(self.svc.db.get_revision_by_id(rev)["snapshot_json"])
        snapshot["topics"][0]["content"] = "```\nUnclosed old document"
        with self.svc.db.get_connection() as conn:
            conn.execute("UPDATE revisions SET snapshot_json=? WHERE rev_id=?", (json.dumps(snapshot), rev))
            conn.commit()
        raw = (self.cfg.decisions_dir / "a.md").read_bytes()
        for call in [lambda: self.svc.restore_single_topic("a", rev, expected_version=1, request_id="bad-snapshot"), lambda: self.svc.rollback_full(rev)]:
            with self.assertRaises(TopicValidationError):
                call()
            self.assertEqual((self.cfg.decisions_dir / "a.md").read_bytes(), raw)
            self.assertEqual(self.svc.db.get_topic("a")["version"], 1)
            with self.svc.db.get_connection() as conn:
                self.assertIsNone(conn.execute("SELECT request_id FROM idempotency_keys WHERE request_id='bad-snapshot'").fetchone())

    def test_git_subprocess_has_a_finite_timeout(self):
        self.svc.git._git_bin = sys.executable
        with patch("core.git_engine.GIT_TIMEOUT", 0.1):
            ok, _, error = self.svc.git.run_git(["-c", "import time; time.sleep(5)"])
        self.assertFalse(ok)
        self.assertIn("超时", error)

    def test_full_rollback_rejects_case_aliases_in_old_snapshot(self):
        self.svc.save_topic("a", {"title": "Keep current"})
        revision = self.svc.db.get_revisions()[0]["rev_id"]
        row = self.svc.db.get_revision_by_id(revision)
        snap = json.loads(row["snapshot_json"])
        snap["topics"].append(dict(snap["topics"][0], id="A"))
        with self.svc.db.get_connection() as conn:
            conn.execute("UPDATE revisions SET snapshot_json=? WHERE rev_id=?", (json.dumps(snap), revision))
            conn.commit()
        raw = (self.cfg.decisions_dir / "a.md").read_bytes()
        with self.assertRaises((TopicValidationError, ValueError)):
            self.svc.rollback_full(revision)
        self.assertEqual((self.cfg.decisions_dir / "a.md").read_bytes(), raw)
        self.assertIsNone(self.svc.db.get_topic("A"))

    def test_metadata_read_does_not_scan_markdown_or_duplicate_full_export(self):
        self.svc.save_topic("a", {"title": "Topic", "new_user_opinion": "User", "new_agent_reply": "Agent"})
        with patch.object(self.app.parser, "count_rounds", side_effect=AssertionError("full file scan")):
            meta = self.app.load_all_topics_meta()
        self.assertEqual(len(meta), 1)
        self.assertEqual(meta[0]["rounds_count"], 1)
        self.assertEqual(meta[0]["last_agent_reply"], "Agent")

    def test_change_summary_is_not_presented_as_agent_reply(self):
        self.svc.save_topic("a", {"title": "Topic", "new_agent_reply": "Actual reply", "commit_message": "First change"})
        self.svc.save_topic("a", {"commit_message": "Metadata-only change"}, expected_version=1)
        self.assertEqual(self.app.load_all_topics_meta()[0]["last_agent_reply"], "Actual reply")

    def test_id_validation_does_not_load_all_topic_bodies(self):
        self.svc.save_topic("a", {"title": "Topic"})
        with patch.object(self.svc.db, "get_all_topics", side_effect=AssertionError("all bodies loaded")):
            self.assertEqual(self.svc.validate_topic_id("a"), "a")
            with self.assertRaises(TopicValidationError):
                self.svc.validate_topic_id("A")

    def test_history_list_does_not_decode_full_snapshots(self):
        self.svc.save_topic("a", {"title": "Topic", "content_override": "UNIQUE_FULL_BODY_MARKER" * 2000})
        original = json.loads
        def guard(value, *args, **kwargs):
            if isinstance(value, str) and "UNIQUE_FULL_BODY_MARKER" in value:
                raise AssertionError("history decoded full snapshot")
            return original(value, *args, **kwargs)
        with patch("core.db.json.loads", side_effect=guard):
            revisions = self.svc.db.get_revisions()
        self.assertIn("a", revisions[0]["snapshot_topic_ids"])

    def test_legacy_history_cache_backfills_once_without_changing_snapshot(self):
        self.svc.save_topic("a", {"title": "Legacy", "content_override": "Keep full snapshot"})
        rev = self.svc.db.get_revisions()[0]["rev_id"]
        original = self.svc.db.get_revision_by_id(rev)["snapshot_json"]
        with self.svc.db.get_connection() as conn:
            conn.execute("UPDATE revisions SET snapshot_topic_ids=NULL WHERE rev_id=?", (rev,))
            conn.commit()
        self.assertEqual(self.svc.db.get_revisions()[0]["snapshot_topic_ids"], ["a"])
        self.assertEqual(self.svc.db.get_revision_by_id(rev)["snapshot_json"], original)
        with self.svc.db.get_connection() as conn:
            self.assertEqual(json.loads(conn.execute("SELECT snapshot_topic_ids FROM revisions WHERE rev_id=?", (rev,)).fetchone()[0]), ["a"])

    def start_http(self):
        httpd = DashboardHTTPServer(("127.0.0.1", 0), make_handler(self.app))
        httpd.RequestHandlerClass.log_message = lambda *args: None
        worker = threading.Thread(target=httpd.serve_forever, daemon=True)
        worker.start()
        def stop():
            httpd.shutdown()
            httpd.server_close()
            worker.join(5)
        self.addCleanup(stop)
        return httpd.server_port

    def post(self, port, path, payload, request_id):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            conn.request("POST", path, json.dumps(payload), {"Content-Type": "application/json", "X-Request-ID": request_id})
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def test_http_parallel_writes_keep_version_check_inside_project_lock(self):
        port = self.start_http()
        for initial, version in [(False, None), (True, 1)]:
            if initial:
                self.assertEqual(self.svc.db.get_topic("a")["version"], 1)
            gate = threading.Barrier(2)
            def send(index):
                gate.wait(5)
                payload = {"title": str(index)}
                if version is not None:
                    payload["expected_version"] = version
                return self.post(port, "/api/topic/a/save", payload, f"{initial}-{index}")[0]
            with ThreadPoolExecutor(max_workers=2) as pool:
                statuses = list(pool.map(send, range(2)))
            self.assertEqual(sorted(statuses), [200, 409 if initial else 428])
            self.assertTrue(self.svc.recovery.check_consistency()["consistent"])
        self.assertEqual(self.svc.db.get_topic("a")["version"], 2)

    def test_deleted_topic_restore_replays_same_http_request_without_version(self):
        empty_rev = self.svc.db.get_revisions()[0]["rev_id"]
        self.svc.save_topic("a", {"title": "Restore me"})
        own_rev = self.svc.db.get_revisions()[0]["rev_id"]
        self.svc.restore_single_topic("a", empty_rev, expected_version=1)
        port = self.start_http()
        payload = {"rev_id": own_rev, "reason": "Original request"}
        first = self.post(port, "/api/topic/a/restore", payload, "restore-lost")
        self.assertEqual(first[0], 200)
        again = self.post(port, "/api/topic/a/restore", payload, "restore-lost")
        self.assertEqual(again, first)
        different = self.post(port, "/api/topic/a/restore", dict(payload, reason="Changed"), "restore-lost")
        self.assertEqual(different[0], 428)
        self.assertEqual(self.svc.db.get_topic("a")["version"], first[1]["new_version"])

    def test_idle_browser_socket_does_not_block_other_requests(self):
        httpd = DashboardHTTPServer(("127.0.0.1", 0), make_handler(self.app))
        httpd.RequestHandlerClass.log_message = lambda *args: None
        worker = threading.Thread(target=httpd.serve_forever, daemon=True)
        worker.start()
        idle = socket.create_connection(httpd.server_address)
        conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=1)
        try:
            conn.request("GET", "/api/topics")
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
        finally:
            idle.close()
            conn.close()
            httpd.shutdown()
            httpd.server_close()
            worker.join(5)


if __name__ == "__main__":
    unittest.main()
