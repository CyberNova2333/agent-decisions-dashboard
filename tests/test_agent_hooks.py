import contextlib
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path

from core.agent_hooks import AgentHooks, HookError, main
from core.config import Config
from core.server import DashboardServer, DashboardHTTPServer, make_handler


class AgentHookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cfg = Config({"git_commit": {"enabled": False}}, self.root)
        self.app = DashboardServer(self.cfg)
        self.receipt = self.app.service.create_topic({"id": "a", "title": "Decision", "workflow_state": "decided",
            "decision_outcome": "accepted", "content_override": "Start\n\nKeep complete requirement"}, request_id="first")
        self.httpd = DashboardHTTPServer(("127.0.0.1", 0), make_handler(self.app))
        self.httpd.RequestHandlerClass.log_message = lambda *args: None
        self.worker = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.worker.start()
        self.addCleanup(self.stop)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        self.hooks = AgentHooks(self.cfg, self.url)

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.worker.join(5)

    def test_before_and_after_are_read_only_and_preserve_full_context(self):
        before = (self.app.db.get_all_topics(), self.app.db.get_revisions(), (self.cfg.decisions_dir / "a.md").read_bytes())
        context = self.hooks.before_task(topic_id="a")
        self.assertIn("Keep complete requirement", context["active_decisions"][0]["content"])
        report = self.hooks.after_write("a", self.receipt)
        self.assertEqual(report["status"], "checked")
        self.assertFalse(report["git_committed"])
        self.assertEqual(before, (self.app.db.get_all_topics(), self.app.db.get_revisions(), (self.cfg.decisions_dir / "a.md").read_bytes()))

    def test_wrong_project_and_missing_topic_fail_closed(self):
        wrong = AgentHooks(Config({}, self.root / "wrong-project"), self.url)
        with self.assertRaises(HookError):
            wrong.before_task()
        with self.assertRaises(HookError):
            self.hooks.before_task(topic_id="missing")

    def test_stale_or_partial_receipt_is_not_confirmed(self):
        for data in [dict(self.receipt, export_status="failed"), dict(self.receipt, git_status="pending"),
                     dict(self.receipt, new_version=True), dict(self.receipt, topic_id="another"),
                     dict(self.receipt, topic=["invalid"]), {"status": "success", "new_version": 1}]:
            with self.subTest(data=data), self.assertRaises(HookError):
                self.hooks.after_write("a", data)
        self.app.service.save_topic("a", {"title": "Newer decision"}, expected_version=1)
        with self.assertRaises(HookError):
            self.hooks.after_write("a", self.receipt)

    def test_drift_and_offline_do_not_become_empty_context(self):
        path = self.cfg.decisions_dir / "a.md"
        path.write_text(path.read_text(encoding="utf-8").replace("Keep complete requirement", "Unsaved change"), encoding="utf-8")
        with self.assertRaises(HookError):
            self.hooks.before_task()
        self.httpd.shutdown()
        self.httpd.server_close()
        with self.assertRaises(HookError):
            self.hooks.before_task()

    def test_remote_and_redirect_style_urls_are_rejected(self):
        for url in ["https://127.0.0.1:8765", "http://example.com", "http://127.0.0.1:8765/path",
                    "http://user:pass@localhost:8765", "http://localhost:8765#fragment"]:
            with self.subTest(url=url), self.assertRaises(HookError):
                AgentHooks(self.cfg, url)

    def test_explicit_deferred_topic_still_returns_its_record(self):
        self.app.service.save_topic("a", {"decision_outcome": "deferred"}, expected_version=1)
        context = self.hooks.before_task(topic_id="a")
        self.assertEqual(context["active_decisions"], [])
        self.assertEqual(context["requested_topic"]["workflow_state"], "deferred")
        self.assertEqual(context["requested_topic"]["decision_outcome"], "accepted")
        self.assertEqual(context["deferred_topics"][0]["decision_outcome"], "accepted")
        self.assertIn("Keep complete requirement", context["requested_topic"]["core_content"])

    def test_cli_exit_code_and_outputs(self):
        cfg = self.root / "dashboard.config.json"
        cfg.write_text('{}', encoding="utf-8")
        receipt = self.root / "receipt.json"
        receipt.write_text(json.dumps(self.receipt), encoding="utf-8")
        args = ["--config", str(cfg), "--url", self.url]
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(main(args + ["before-task", "--topic", "a"]), 0)
            self.assertEqual(main(args + ["after-write", "--topic", "a", "--receipt", str(receipt)]), 0)
            self.assertEqual(main(args + ["before-task", "--topic", "missing"]), 2)
        self.assertIn('"status": "blocked"', stderr.getvalue())
        self.assertIn('"status": "checked"', stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
