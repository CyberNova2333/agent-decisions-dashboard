# -*- coding: utf-8 -*-
"""
Agent Decisions Dashboard - Rework Regressions (N01 - N17)
基于最新代码审查与边界测试用例整理：
- N01: 校验合法 Origin 请求正常响应不发生断连
- N02: 两个并发写入者基于同一基线版本无法全部成功 (CAS 乐观锁)
- N03: 数据库写入异常时重试不重复追加讨论轮次
- N04: 导出重试时自动续做未完成的 Git 提交阶段
- N05: create_topic 幂等重放时自动修复失败的元数据导出
- N06: 单议题恢复完整保留仅含变更说明的轮次
- N07: 双端摘要一致性检查精准识别数据库独占的讨论修改
- N08: 双端一致性检查精准识别导出的决策结论漂移
- N09: 重建索引时临时读取失败绝不误删数据库议题
- N10: 重建与回滚严格校验议题 ID 路径安全，阻断穿透攻击
- N11: 全库回滚采用单调递增代次，杜绝旧并发令牌 (ABA) 复用
- N12: 回滚归档操作异常时绝不删除原有源文件
- N13: 核验接口拒绝空 commit hash (返回 400)
- N14: 核验接口拒绝弱类型字符串 'false' (返回 400)
- N15: 保存前检测权威文件被直接篡改的未索引漂移并拒绝覆盖
- N16: 外部并发 git add 暂存的文件绝不被台账自动提交混入
- N17: 合法的显式布尔值 False 正常保持已实现状态
"""

import contextlib
import http.client
import json
import os
import sqlite3
import subprocess
import tempfile
import threading
import traceback
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from core.config import Config
from core.decision_service import DecisionService, VersionConflictError
from core.server import DashboardServer, make_handler
from http.server import HTTPServer


class TestReworkRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="dashboard-rework-regression-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cfg = Config({"git_commit": {"enabled": False}}, self.root)
        self.svc = DecisionService(self.cfg)
        self.repo_web = Path(__file__).resolve().parent.parent / "web"

    def md(self, tid="a") -> Path:
        return self.cfg.decisions_dir / f"{tid}.md"

    def save(self, tid="a", **extra):
        data = {
            "title": "Topic A",
            "section": "Backend",
            "workflow_state": "decided",
            "decision_outcome": "accepted",
            "content_override": "Original body",
            "new_user_opinion": "Human instruction",
            "new_agent_reply": "Agent reply",
            "commit_message": "Recorded decision",
        }
        data.update(extra)
        row = self.svc.db.get_topic(tid)
        return self.svc.save_topic(tid, data, expected_version=row["version"] if row else None)

    def parse(self, tid="a"):
        return self.svc.parser.parse_markdown_file(self.md(tid))

    def git_on(self):
        for cmd in [["init"], ["config", "user.name", "Regression"], ["config", "user.email", "test@example.invalid"]]:
            subprocess.run(["git"] + cmd, cwd=self.root, check=True, capture_output=True)
        (self.root / "README.md").write_text("isolated audit fixture", encoding="utf-8")
        for cmd in [["add", "README.md"], ["commit", "-m", "initial fixture"]]:
            subprocess.run(["git"] + cmd, cwd=self.root, check=True, capture_output=True)
        self.cfg = Config({"git_commit": {"enabled": True}}, self.root)
        self.svc = DecisionService(self.cfg)

    @contextlib.contextmanager
    def http(self):
        app = DashboardServer(self.cfg, web_dir=self.repo_web)
        errors = []

        class RecordingServer(HTTPServer):
            def handle_error(self, request, client_address):
                errors.append(traceback.format_exc())

        handler_cls = make_handler(app)
        handler_cls.log_message = lambda *a: None
        server = RecordingServer(("127.0.0.1", 0), handler_cls)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server, app, errors
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def request(self, server, path, payload, origin=None):
        con = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        try:
            headers = {"Content-Type": "application/json"}
            if origin:
                headers["Origin"] = origin
            con.request("POST", path, json.dumps(payload), headers)
            r = con.getresponse()
            body = r.read().decode("utf-8")
            return {"status": r.status, "body": json.loads(body)}
        except Exception as e:
            return {"status": None, "exception": f"{type(e).__name__}: {e}"}
        finally:
            con.close()

    def test_N01_same_origin_post_must_receive_response(self):
        with self.http() as (server, app, errors):
            origin = f"http://127.0.0.1:{server.server_port}"
            result = self.request(server, "/api/topic/a/save", {"title": "Browser save"}, origin)
            self.assertEqual(result["status"], 200, f"Legitimate Origin request disconnected: {result}")

    def test_N02_two_service_writers_must_not_both_accept_v1(self):
        self.save()
        barrier = threading.Barrier(2)

        def writer(title):
            try:
                # Race at admission; the project lock now serializes baseline reads.
                barrier.wait(timeout=5)
                r = self.svc.save_topic("a", {"title": title}, expected_version=1)
                return {"status": "success", "version": r["new_version"]}
            except VersionConflictError:
                return {"status": "conflict"}
            except Exception as e:
                return {"status": "error", "error": repr(e)}

        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="audit-writer") as pool:
            result = list(pool.map(writer, ["Writer A", "Writer B"]))

        self.assertEqual(sum(x["status"] == "success" for x in result), 1, "Both stale-baseline writers succeeded")
        self.assertEqual(sorted(x["status"] for x in result), ["conflict", "success"])

    def test_N03_database_failure_must_not_duplicate_round_on_retry(self):
        self.save()
        before = self.md().read_text(encoding="utf-8")
        payload = {"title": "Topic A", "new_user_opinion": "ONLY-ONCE-RETRY", "new_agent_reply": "reply"}
        with patch.object(self.svc.db, "upsert_topic", side_effect=sqlite3.OperationalError("injected DB write failure")):
            try:
                self.svc.save_topic("a", payload, expected_version=1, request_id="retry-after-db-error")
            except sqlite3.OperationalError:
                pass

        replay = self.svc.save_topic("a", payload, expected_version=1, request_id="retry-after-db-error")
        rounds = self.parse()["rounds"]
        count = sum(r["user_opinion"] == "ONLY-ONCE-RETRY" for r in rounds)
        self.assertEqual(count, 1, "Same failed request appended its user round twice")

    def test_N04_export_retry_must_finish_git_phase(self):
        self.git_on()
        head = self.svc.git.get_head_hash()
        payload = {"title": "Applied once", "new_user_opinion": "Round 1"}
        with patch.object(self.svc.recovery, "sync_metadata_json", side_effect=OSError("injected export failure")):
            try:
                self.svc.save_topic("a", payload, request_id="export-retry")
            except OSError:
                pass

        with patch.object(self.svc.git, "commit_decision", wraps=self.svc.git.commit_decision) as commit:
            result = self.svc.save_topic("a", payload, request_id="export-retry")

        self.assertNotEqual(result["git_status"], "pending", "Replay never attempts remaining Git stage")

    def test_N05_create_replay_must_repair_failed_export(self):
        payload = {"id": "a", "title": "Created topic"}
        with patch.object(self.svc.recovery, "sync_metadata_json", side_effect=OSError("injected export failure")):
            try:
                self.svc.create_topic(payload, request_id="create-export-retry")
            except OSError:
                pass
        result = self.svc.create_topic(payload, request_id="create-export-retry")
        self.assertEqual(result["export_status"], "ok", "Create replay skips export compensation entirely")

    def test_N06_restore_must_preserve_commit_only_round(self):
        self.save(new_user_opinion="", new_agent_reply="", commit_message="ONLY-CHANGE-NOTE")
        old = self.parse()["rounds"]
        rev = self.svc.db.get_revisions()[0]["rev_id"]
        self.save(title="Later")
        self.svc.restore_single_topic("a", rev)
        new = self.parse()["rounds"]
        self.assertEqual(len(new), len(old), "A round containing only a change note disappeared during restore")

    def test_N07_consistency_must_detect_database_discussion_drift(self):
        self.save()
        with self.svc.db.get_connection() as conn:
            conn.execute("UPDATE topics SET discussion_json=? WHERE id=?", (json.dumps([{"key": "第 1 轮用户意见", "val": "DATABASE-ONLY CHANGE"}]), "a"))
            conn.commit()
        report = self.svc.recovery.check_consistency()
        self.assertFalse(report["consistent"], "DB discussion changes are not compared with disk rounds")

    def test_N08_consistency_must_detect_exported_outcome_drift(self):
        self.save()
        meta = json.loads(self.cfg.metadata_json_path.read_text(encoding="utf-8"))
        meta["topics"][0]["decision_outcome"] = "rejected"
        self.cfg.metadata_json_path.write_text(json.dumps(meta), encoding="utf-8")
        report = self.svc.recovery.check_consistency()
        self.assertFalse(report["consistent"], "Exported decision outcome is not validated")

    def test_N09_failed_rebuild_must_not_remove_unreadable_topic(self):
        self.save("a")
        self.save("b")
        original = self.svc.recovery.parser.parse_markdown_file

        def read(p):
            if p.name == "b.md":
                raise PermissionError("injected temporary read error")
            return original(p)

        with patch.object(self.svc.recovery.parser, "parse_markdown_file", side_effect=read):
            try:
                self.svc.recovery.rebuild_index_from_markdown()
            except Exception:
                pass
        topics = [t["id"] for t in self.svc.db.get_all_topics()]
        self.assertIn("b", topics, "A temporarily unreadable source was treated as a deleted topic")

    def test_N10_rebuild_and_rollback_must_reject_escaping_id(self):
        self.cfg.decisions_dir.mkdir(parents=True, exist_ok=True)
        outside = self.root / "outside-canary.md"
        outside.write_text("UNRELATED-USER-FILE", encoding="utf-8")
        text = self.svc.parser.serialize_markdown(
            topic_id="../outside-canary",
            title="Invalid imported ID",
            lifecycle_badge="decided",
            decision_status="accepted",
            impl_status="not_started",
            priority="normal",
            obj="Backend",
            func="API",
            core_content="RESTORED-OVERWRITE",
            existing_rounds=[],
        )
        self.md("imported").write_text(text, encoding="utf-8")
        try:
            self.svc.recovery.rebuild_index_from_markdown()
            rev = self.svc.db.commit_revision("AUDIT", "snapshot imported state")["rev_id"]
            self.svc.rollback_full(rev)
        except Exception:
            pass
        contents = outside.read_text(encoding="utf-8")
        self.assertEqual(contents, "UNRELATED-USER-FILE", "Imported frontmatter ID bypassed path validation and overwrote a file outside decisions/")

    def test_N11_full_rollback_must_not_reuse_old_concurrency_token(self):
        self.save(title="v1 baseline")
        rev1 = self.svc.db.get_revisions()[0]["rev_id"]
        self.save(title="v2 OLD BRANCH")
        self.save(title="v3 old branch")
        self.svc.rollback_full(rev1)
        restored_ver = self.svc.db.get_topic("a")["version"]
        branch = self.svc.save_topic("a", {"title": "NEW BRANCH"}, expected_version=restored_ver)
        rejected = False
        try:
            self.svc.save_topic("a", {"title": "STALE OLD V2 CLIENT"}, expected_version=2)
        except VersionConflictError:
            rejected = True
        self.assertTrue(rejected, "Rollback reused v2, allowing an old-v2 client to overwrite new branch state")

    def test_N12_failed_archival_must_not_unlink_original(self):
        self.save()
        rev = self.svc.db.get_revisions()[0]["rev_id"]
        draft = self.md("untracked-draft")
        draft.write_text("ONLY-COPY-OF-UNCOMMITTED-DRAFT", encoding="utf-8")
        with patch("core.decision_service.shutil.move", side_effect=OSError("injected archive/disk failure")):
            try:
                self.svc.rollback_full(rev)
            except Exception:
                pass
        self.assertTrue(draft.exists(), "Archive failure falls back to deleting the only source file")

    def test_N13_verify_must_reject_null_commit_with_400(self):
        self.save()
        with self.http() as (server, app, errors):
            result = self.request(server, "/api/topic/a/verify", {"impl_commit": None, "expected_version": 1})
            self.assertEqual(result["status"], 400, "Malformed verification input aborts connection instead of returning validation error")

    def test_N14_verify_must_not_treat_false_string_as_true(self):
        self.save()
        with self.http() as (server, app, errors):
            result = self.request(server, "/api/topic/a/verify", {"impl_commit": "abc1234", "mark_verified": "false", "expected_version": 1})
            self.assertEqual(result["status"], 400, "String false silently marks a topic VERIFIED")

    def test_N15_save_must_not_overwrite_unindexed_authoritative_metadata(self):
        self.save()
        text = self.md().read_text(encoding="utf-8").replace('title: "Topic A"', 'title: "EXTERNAL AUTHORITATIVE TITLE"')
        self.md().write_text(text, encoding="utf-8")
        rejected = False
        try:
            self.svc.save_topic("a", {"title": "Topic A", "new_user_opinion": "Client update"}, expected_version=1)
        except Exception:
            rejected = True
        self.assertTrue(rejected or self.parse()["title"] == "EXTERNAL AUTHORITATIVE TITLE", "DB-only version check ignored known authoritative-file drift")

    def test_N16_git_final_command_excludes_late_unrelated_stage(self):
        self.git_on()
        userfile = self.root / "unrelated-user-code.py"
        userfile.write_text('print("user work")\n', encoding="utf-8")
        original = self.svc.git.run_git
        injected = False

        def run(args):
            nonlocal injected
            if args and args[0] == "commit" and not injected:
                injected = True
                subprocess.run(["git", "add", "unrelated-user-code.py"], cwd=self.root, check=True, capture_output=True)
            return original(args)

        with patch.object(self.svc.git, "run_git", side_effect=run):
            result = self.save()

        committed = subprocess.run(["git", "show", "--pretty=format:", "--name-only", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.splitlines()
        staged = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=self.root, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertEqual(result["git_status"], "committed")
        self.assertNotIn("unrelated-user-code.py", committed)
        self.assertIn("unrelated-user-code.py", staged)

    def test_N17_valid_false_boolean_preserves_implemented_state(self):
        self.save()
        with self.http() as (server, app, errors):
            result = self.request(server, "/api/topic/a/verify", {"impl_commit": "abc1234", "mark_verified": False, "expected_version": 1})
            self.assertEqual(result["status"], 200)
            self.assertEqual(app.db.get_topic("a")["implementation_state"], "implemented")


if __name__ == "__main__":
    unittest.main()
