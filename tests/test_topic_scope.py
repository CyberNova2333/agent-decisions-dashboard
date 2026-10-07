"""Regression tests for product-board topic scoping."""
import tempfile
import unittest
from pathlib import Path

from core.agent_context import AgentContextEngine
from core.config import Config
from core.decision_service import DecisionService
from core.server import DashboardServer


class TopicScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cfg = Config({"topic_scope": {"active_topic_ids": ["keep"]},
                           "git_commit": {"enabled": False}}, self.root)
        self.svc = DecisionService(self.cfg)
        self.svc.save_topic("keep", {"title": "Visible", "workflow_state": "decided",
                                      "decision_outcome": "accepted"})
        self.svc.save_topic("archive", {"title": "Archived", "workflow_state": "decided",
                                         "decision_outcome": "accepted"})
        self.svc.db.record_changelog("[Archived](#archive)", "Hidden change", "test")
        self.svc.db.record_changelog("全局维护", "Visible global change", "test")

    def test_topic_list_and_agent_context_use_active_scope(self):
        app = DashboardServer.__new__(DashboardServer)
        app.config = self.cfg
        app.db = self.svc.db
        app.service = self.svc
        visible = app.load_all_topics_meta()
        self.assertEqual([item["id"] for item in visible], ["keep"])

        context = AgentContextEngine(self.cfg, self.svc.db).query_context()
        self.assertEqual(context["counts"]["total_matched"], 1)
        self.assertEqual(context["active_decisions"][0]["id"], "keep")
        self.assertEqual([item["change"] for item in app.load_changelog()], ["Visible global change"])

    def test_unscoped_config_keeps_legacy_behavior(self):
        cfg = Config({"git_commit": {"enabled": False}}, self.root)
        context = AgentContextEngine(cfg, self.svc.db).query_context()
        self.assertEqual(context["counts"]["total_matched"], 2)


if __name__ == "__main__":
    unittest.main()
