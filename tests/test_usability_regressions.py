"""Reply correction, multiline data and partially accepted decisions."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core.config import Config
from core.server import DashboardServer
from core.decision_service import TopicValidationError
from core.db import VersionConflictError


class UsabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = DashboardServer(Config({'git_commit': {'enabled': False}}, Path(self.tmp.name)))
        self.svc = self.app.service
        self.svc.create_topic({'id': 'a', 'title': 'Topic', 'new_user_opinion': 'First\nSecond\n\nFourth',
                               'new_agent_reply': 'Agent\nReply', 'commit_message': 'original'})

    def detail(self):
        return self.svc.parser.parse_markdown_file(self.svc.config.decisions_dir / 'a.md')

    def test_amend_preserves_history_round_count_other_party_and_replay(self):
        before = self.detail()
        payload = {'edit_latest_round': True, 'new_agent_reply': 'Corrected\n\nReply', 'commit_message': 'correction'}
        result = self.svc.save_topic('a', payload, expected_version=1, request_id='correct')
        self.assertEqual(len(self.detail()['rounds']), 1)
        self.assertEqual(self.detail()['rounds'][0]['user_opinion'], before['rounds'][0]['user_opinion'])
        self.assertEqual(self.detail()['rounds'][0]['agent_reply'], 'Corrected\n\nReply')
        self.assertEqual(self.app.load_all_topics_meta()[0]['last_agent_reply'], 'Corrected\n\nReply')
        replay = self.svc.save_topic('a', payload, expected_version=1, request_id='correct')
        self.assertEqual(replay['new_version'], 2)
        self.svc.restore_single_topic('a', result['prior_rev_id'], expected_version=2)
        for key in ('user_opinion', 'agent_reply', 'commit_message'):
            self.assertEqual(self.detail()['rounds'][0][key], before['rounds'][0][key])
        self.assertTrue(self.svc.recovery.check_consistency()['consistent'])

    def test_clear_latest_reply_does_not_show_an_older_round(self):
        self.svc.save_topic('a', {'new_agent_reply': 'Latest reply'}, expected_version=1)
        self.svc.save_topic('a', {'edit_latest_round': True, 'new_agent_reply': ''}, expected_version=2)
        self.assertEqual(self.app.load_all_topics_meta()[0]['latest_round_user_opinion'], '')
        self.assertEqual(self.app.load_all_topics_meta()[0]['latest_round_agent_reply'], '')
        self.assertEqual(len(self.detail()['rounds']), 2)
        self.assertTrue(self.svc.recovery.check_consistency()['consistent'])

    def test_amend_rejects_stale_version_and_missing_version(self):
        with self.assertRaises(TopicValidationError):
            self.svc.save_topic('a', {'edit_latest_round': True, 'new_user_opinion': 'Changed'})
        self.svc.save_topic('a', {'new_user_opinion': 'Next round'}, expected_version=1)
        with self.assertRaises(VersionConflictError):
            self.svc.save_topic('a', {'edit_latest_round': True, 'new_user_opinion': 'Old correction'}, expected_version=1)
        self.assertEqual(self.detail()['rounds'][-1]['user_opinion'], 'Next round')

    def test_amend_retry_after_file_write_keeps_original_snapshot(self):
        before = self.detail()['rounds']
        payload = {'edit_latest_round': True, 'new_user_opinion': 'Amended\nReply'}
        with patch.object(self.svc.db, 'upsert_topic', side_effect=OSError('index failure')):
            with self.assertRaises(OSError):
                self.svc.save_topic('a', payload, expected_version=1, request_id='retry-amend')
        result = self.svc.save_topic('a', payload, expected_version=1, request_id='retry-amend')
        self.assertTrue(self.svc.recovery.check_consistency()['consistent'])
        self.assertEqual(len(self.detail()['rounds']), 1)
        self.svc.restore_single_topic('a', result['prior_rev_id'], expected_version=2)
        for key in ('user_opinion', 'agent_reply', 'commit_message'):
            self.assertEqual(self.detail()['rounds'][0][key], before[0][key])

    def test_amend_does_not_overwrite_unindexed_same_version_reply(self):
        path = self.svc.config.decisions_dir / 'a.md'
        path.write_text(path.read_text(encoding='utf-8').replace('Agent\nReply', 'External\nReply'), encoding='utf-8')
        raw = path.read_bytes()
        with self.assertRaises(VersionConflictError):
            self.svc.save_topic('a', {'edit_latest_round': True, 'new_agent_reply': 'Stale correction'}, expected_version=1)
        self.assertEqual(path.read_bytes(), raw)

    def test_partial_acceptance_roundtrips_without_turning_whole_proposal_into_rule(self):
        with self.assertRaises(TopicValidationError):
            self.svc.save_topic('a', {'decision_outcome': 'partially_accepted'}, expected_version=1)
        self.svc.save_topic('a', {'decision_outcome': 'partially_accepted', 'workflow_state': 'decided',
                                 'new_user_opinion': 'Agree A\nReserve B'}, expected_version=1)
        self.assertEqual(self.detail()['decision_outcome'], 'partially_accepted')
        self.assertEqual(self.app.overview_from_topics(self.app.load_all_topics_meta())[0][0]['outcome_label'], '部分同意')
        context = self.app.agent.query_context(topic_id='a')
        self.assertEqual(context['active_decisions'], [])
        self.assertEqual(context['pending_requirements'][0]['decision_outcome'], 'partially_accepted')
        self.assertIn('部分同意', self.app.agent.format_as_markdown(context))
        self.svc.recovery.rebuild_index_from_markdown()
        self.assertTrue(self.svc.recovery.check_consistency()['consistent'])

    def test_multiline_and_implementation_status_agree_in_file_index_and_list(self):
        reply = 'Line one\nLine two\n\nLine four\n| A | B |\n| --- | --- |\n| x | y |'
        self.svc.save_topic('a', {'new_user_opinion': reply, 'implementation_state': 'implemented'}, expected_version=1)
        self.assertEqual(self.detail()['rounds'][-1]['user_opinion'], reply)
        meta = self.app.load_all_topics_meta()[0]
        self.assertEqual(meta['last_user_opinion'], reply)
        self.assertEqual(meta['implementation_state'], 'implemented')
        self.assertEqual(self.detail()['implementation_state'], 'implemented')
        self.assertTrue(self.svc.recovery.check_consistency()['consistent'])

    def test_status_only_save_reports_actual_round_without_appending(self):
        result = self.svc.save_topic('a', {'implementation_state': 'in_progress'}, expected_version=1)
        self.assertEqual(result['round'], 1)
        self.assertEqual(len(self.detail()['rounds']), 1)
        created = self.svc.create_topic({'id': 'empty', 'title': 'No discussions'})
        self.assertEqual(created['round'], 0)

    def test_delete_topic_archives_records_snapshot_and_supports_undo_restore(self):
        with self.assertRaises(VersionConflictError):
            self.svc.delete_topic('a', expected_version=99, request_id='del-bad-ver')
        result = self.svc.delete_topic('a', expected_version=1, request_id='del-1', reason='archive topic a')
        self.assertTrue(result['removed'])
        self.assertIsNotNone(result['prior_rev_id'])
        self.assertIsNone(self.svc.db.get_topic('a'))
        self.assertFalse((self.svc.config.decisions_dir / 'a.md').exists())
        self.assertTrue(self.svc.recovery.check_consistency()['consistent'])
        replay = self.svc.delete_topic('a', expected_version=1, request_id='del-1', reason='archive topic a')
        self.assertTrue(replay.get('idempotent_replay'))
        self.assertEqual(replay['prior_rev_id'], result['prior_rev_id'])
        restored = self.svc.restore_single_topic('a', result['prior_rev_id'], request_id='undo-del-1')
        self.assertEqual(restored['topic']['id'], 'a')
        self.assertTrue((self.svc.config.decisions_dir / 'a.md').exists())
        self.assertEqual(self.detail()['title'], 'Topic')
        self.assertTrue(self.svc.recovery.check_consistency()['consistent'])
