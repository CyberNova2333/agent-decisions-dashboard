"""Regression checks for the ledger's documented, everyday workflows."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from core.agent_context import AgentContextEngine
from core.config import Config, load_config
from core.decision_service import DecisionService, TopicValidationError
from core.server import DashboardServer


class ProductContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cfg = Config({"git_commit": {"enabled": False}}, self.root)
        self.svc = DecisionService(self.cfg)

    def test_comment_only_save_preserves_all_existing_states(self):
        self.svc.save_topic("a", {"title": "Keep title", "workflow_state": "decided", "decision_outcome": "rejected",
                                   "rejection_reason": "Keep reason", "implementation_state": "verified"})
        before = self.svc.db.get_topic("a")
        self.svc.save_topic("a", {"new_user_opinion": "One more detail"}, expected_version=1)
        after = self.svc.db.get_topic("a")
        for key in ("title", "workflow_state", "decision_outcome", "rejection_reason", "implementation_state", "decision_status"):
            self.assertEqual(after[key], before[key], key)
        self.assertTrue(self.svc.recovery.check_consistency()["consistent"])

    def test_rejected_update_can_retain_its_existing_reason(self):
        self.svc.save_topic("a", {"title": "Rejected", "decision_outcome": "rejected", "rejection_reason": "Keep reason"})
        self.svc.save_topic("a", {"decision_outcome": "rejected", "new_agent_reply": "Noted"}, expected_version=1)
        self.assertEqual(self.svc.db.get_topic("a")["rejection_reason"], "Keep reason")

    def test_core_heading_and_template_like_lines_are_preserved(self):
        body = "# This is a body heading\n\nText\n\n> **锚点** is documentation content"
        self.svc.save_topic("a", {"title": "Envelope title", "content_override": body})
        parsed = self.svc.parser.parse_markdown_file(self.cfg.decisions_dir / "a.md")
        self.assertEqual(parsed["core_content"], body)
        self.assertTrue(self.svc.recovery.check_consistency()["consistent"])

    def test_case_alias_cannot_replace_another_topic(self):
        self.svc.save_topic("alias", {"title": "Original"})
        before = (self.cfg.decisions_dir / "alias.md").read_bytes()
        with self.assertRaises(TopicValidationError):
            self.svc.create_topic({"id": "ALIAS", "title": "Different topic"})
        self.assertEqual((self.cfg.decisions_dir / "alias.md").read_bytes(), before)
        self.assertIsNone(self.svc.db.get_topic("ALIAS"))

    def test_windows_device_names_are_rejected_before_writing(self):
        for topic_id in ("NUL", "con", "COM1", "LPT9"):
            with self.subTest(topic_id=topic_id), self.assertRaises(TopicValidationError):
                self.svc.create_topic({"id": topic_id, "title": "Not a disk file"})

    def test_agent_context_retains_requirements_beyond_the_first_paragraph(self):
        self.svc.save_topic("a", {"title": "Requirement", "workflow_state": "decided", "decision_outcome": "accepted",
                                   "content_override": "Overview\n\nMUST RETAIN THIS LATER REQUIREMENT"})
        agent = AgentContextEngine(self.cfg, self.svc.db)
        context = agent.query_context()
        self.assertIn("MUST RETAIN THIS LATER REQUIREMENT", agent.format_as_markdown(context))

    def test_commit_reference_does_not_imply_implementation(self):
        self.svc.save_topic("a", {"title": "Requirement", "workflow_state": "decided", "decision_outcome": "accepted",
                                   "implementation_state": "not_started", "impl_commit": "reference-only"})
        agent = AgentContextEngine(self.cfg, self.svc.db)
        text = agent.format_as_markdown(agent.query_context())
        self.assertNotIn("已实现", text)
        self.assertIn("not_started", text)

    def test_ambiguous_markdown_is_rejected_without_changing_saved_data(self):
        self.svc.save_topic("a", {"title": "Original", "new_user_opinion": "Keep history"})
        row = self.svc.db.get_topic("a")
        raw = (self.cfg.decisions_dir / "a.md").read_bytes()
        for field, text in [("content_override", "```\nunclosed"),
                            ("content_override", "Text\n\n## 历史讨论与决策记录\n\nHidden"),
                            ("new_user_opinion", "My words\n\n- **团队答复**：not an actual reply"),
                            ("new_user_opinion", "Words\n\n### 第 5 轮讨论\nMore words")]:
            with self.subTest(field=field, text=text), self.assertRaises(TopicValidationError):
                self.svc.save_topic("a", {field: text}, expected_version=1, request_id="rejected-text")
            self.assertEqual(self.svc.db.get_topic("a"), row)
            self.assertEqual((self.cfg.decisions_dir / "a.md").read_bytes(), raw)
        with self.svc.db.get_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM idempotency_keys WHERE request_id='rejected-text'").fetchone()[0], 0)

    def test_missing_authoritative_file_cannot_silently_erase_history(self):
        self.svc.save_topic("a", {"title": "Original", "new_user_opinion": "Keep history"})
        (self.cfg.decisions_dir / "a.md").unlink()
        with self.assertRaises(TopicValidationError):
            self.svc.save_topic("a", {"new_user_opinion": "New"}, expected_version=1)
        self.assertEqual(self.svc.db.get_topic("a")["version"], 1)

    def test_current_overview_tracks_decisions_and_pending_topics(self):
        app = DashboardServer(self.cfg)
        app.service.create_topic({"id": "a", "title": "Choice", "workflow_state": "pending"})
        settled, pending = app.overview_from_topics(app.load_all_topics_meta())
        self.assertEqual(settled, [])
        self.assertEqual([t["topic_ref"] for t in pending], ["a"])
        app.service.save_topic("a", {"workflow_state": "decided", "decision_outcome": "rejected", "rejection_reason": "Reason"}, expected_version=1)
        settled, pending = app.overview_from_topics(app.load_all_topics_meta())
        self.assertEqual(pending, [])
        self.assertEqual(settled[0]["outcome_label"], "已否决")
        app.service.save_topic("a", {"decision_outcome": "superseded"}, expected_version=2)
        self.assertEqual(app.overview_from_topics(app.load_all_topics_meta()), ([], []))

    def test_rebuild_preserves_custom_decision_status_and_sources(self):
        self.svc.save_topic("a", {"title": "Original", "decision_status": "用户已同意", "sources": "docs/spec.md"})
        original_revision = self.svc.db.get_revisions()[0]["rev_id"]
        self.svc.save_topic("a", {"new_user_opinion": "Retain metadata"}, expected_version=1)
        self.svc.record_verification("a", "ref", "reviewer", expected_version=2)
        self.assertEqual(self.svc.parser.parse_markdown_file(self.cfg.decisions_dir / "a.md")["sources"], "docs/spec.md")
        self.svc.restore_single_topic("a", original_revision, expected_version=3)
        self.svc.recovery.rebuild_index_from_markdown()
        row = self.svc.db.get_topic("a")
        self.assertEqual(row["decision_status"], "用户已同意")
        self.assertEqual(row["sources"], "docs/spec.md")
        self.assertTrue(self.svc.recovery.check_consistency()["consistent"])

    def test_unindexed_file_cannot_be_replaced_by_create_or_save(self):
        self.svc.save_topic("a", {"title": "Keep existing file"})
        raw = (self.cfg.decisions_dir / "a.md").read_bytes()
        with self.svc.db.get_connection() as conn:
            conn.execute("DELETE FROM topics WHERE id='a'")
            conn.commit()
        with self.assertRaises(TopicValidationError):
            self.svc.create_topic({"id": "a", "title": "New"})
        with self.assertRaises(TopicValidationError):
            self.svc.save_topic("a", {"title": "New"})
        self.assertEqual((self.cfg.decisions_dir / "a.md").read_bytes(), raw)

    def test_save_rejects_external_changes_to_non_state_metadata(self):
        self.svc.save_topic("a", {"title": "Original", "sources": "old-source", "impl_commit": "old-reference"})
        path = self.cfg.decisions_dir / "a.md"
        original = path.read_bytes()
        row = self.svc.db.get_topic("a")
        from core.db import VersionConflictError
        for before, after in [(b'old-source', b'new-source'), (b'old-reference', b'new-reference')]:
            with self.subTest(before=before):
                edited = original.replace(before, after)
                path.write_bytes(edited)
                self.assertFalse(self.svc.recovery.check_consistency()["consistent"])
                with self.assertRaises(VersionConflictError):
                    self.svc.save_topic("a", {"new_user_opinion": "New"}, expected_version=1)
                self.assertEqual(path.read_bytes(), edited)
                self.assertEqual(self.svc.db.get_topic("a"), row)

    def test_summary_only_metadata_is_never_imported_as_authoritative_content(self):
        self.cfg.decisions_dir.mkdir()
        self.cfg.metadata_json_path.write_text(json.dumps({"topics": [{"id": "ghost", "title": "Summary", "summary": "Truncated"}]}), encoding="utf-8")
        app = DashboardServer(self.cfg)
        self.assertIsNone(app.db.get_topic("ghost"))

    def test_config_relative_paths_are_relative_to_the_config_file(self):
        config_dir = self.root / "project"
        config_dir.mkdir()
        path = config_dir / "dashboard.config.json"
        path.write_text('{"decisions_dir": "ledger"}', encoding="utf-8")
        self.assertEqual(load_config(path).decisions_dir, config_dir / "ledger")

    def test_explicit_bad_config_does_not_silently_fall_back(self):
        bad = self.root / "bad.json"
        bad.write_text('{broken', encoding="utf-8")
        with self.assertRaises(ValueError):
            load_config(bad)
        with self.assertRaises(FileNotFoundError):
            load_config(self.root / "missing.json")

    def test_rebuild_cli_failure_is_reported_with_nonzero_exit(self):
        cfg = self.root / "dashboard.config.json"
        cfg.write_text('{"git_commit": {"enabled": false}}', encoding="utf-8")
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]), PYTHONUTF8="1")
        result = subprocess.run([sys.executable, "-m", "core.server", "--config", str(cfg), "--rebuild-index"],
                                cwd=self.root, env=env, capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(result.returncode, 0, result.stdout)


if __name__ == "__main__":
    unittest.main()
