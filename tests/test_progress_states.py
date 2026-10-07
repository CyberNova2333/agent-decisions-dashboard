"""Agreement, scheduling and implementation must survive independent edits."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.config import Config
from core.server import DashboardServer
from core.decision_service import TopicValidationError, IdempotencyConflictError
from core.db import VersionConflictError


class ProgressStateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.app = DashboardServer(Config({'git_commit': {'enabled': False}}, Path(tmp.name)))
        self.svc = self.app.service

    def detail(self, tid='a'):
        return self.svc.parser.parse_markdown_file(self.svc.config.decisions_dir / (tid + '.md'))

    def create(self, **data):
        return self.svc.create_topic(dict(id='a', title='Review after the pilot', **data))

    def legacy(self, outcome):
        self.create(workflow_state='decided', new_user_opinion='Original words\nKeep both lines')
        path = self.svc.config.decisions_dir / 'a.md'
        raw = path.read_text(encoding='utf-8').replace('decision_outcome: ""', f'decision_outcome: "{outcome}"')
        path.write_text(raw, encoding='utf-8')
        self.svc.recovery.rebuild_index_from_markdown()
        self.assertTrue(self.svc.recovery.check_consistency()['consistent'])
        return path.read_bytes()

    def test_agreement_and_implementation_are_independent_of_waiting(self):
        self.create(workflow_state='deferred', decision_outcome='accepted',
                    new_user_opinion='Agree to wait\nReview after the pilot', implementation_state='in_progress')
        self.svc.save_topic('a', {'new_agent_reply': 'Waiting for pilot evidence'}, expected_version=1)
        self.svc.save_topic('a', {'implementation_state': 'implemented'}, expected_version=2)
        self.assertEqual((self.detail()['workflow_state'], self.detail()['decision_outcome']), ('deferred', 'accepted'))
        self.assertEqual(self.detail()['implementation_state'], 'implemented')
        ctx = self.app.agent.query_context()
        self.assertEqual(ctx['active_decisions'], [])
        self.assertEqual(ctx['pending_requirements'], [])
        self.assertEqual(ctx['deferred_topics'][0]['decision_outcome'], 'accepted')
        md = self.app.agent.format_as_markdown(ctx)
        self.assertIn('Review after the pilot', md)
        self.assertIn('条件未满足时不要推进', md)
        overview, _ = self.app.overview_from_topics(self.app.load_all_topics_meta())
        self.assertIn('推迟再议', overview[0]['outcome_label'])
        self.svc.save_topic('a', {'workflow_state': 'decided'}, expected_version=3)
        self.assertEqual(self.app.agent.query_context()['active_decisions'][0]['decision_outcome'], 'accepted')
        self.assertTrue(self.svc.recovery.check_consistency()['consistent'])

    def test_old_outcome_alias_preserves_existing_consent(self):
        self.create(workflow_state='decided', decision_outcome='accepted')
        payload = {'decision_outcome': 'deferred', 'workflow_state': 'decided', 'new_agent_reply': 'Wait'}
        receipt = self.svc.save_topic('a', payload, expected_version=1, request_id='pause')
        self.assertEqual((self.detail()['workflow_state'], self.detail()['decision_outcome']), ('deferred', 'accepted'))
        replay = self.svc.save_topic('a', payload, expected_version=1, request_id='pause')
        self.assertTrue(replay['is_replay'])
        self.assertEqual(receipt, {key: value for key, value in replay.items() if key != 'is_replay'})
        self.svc.save_topic('a', {'decision_outcome': 'superseded', 'superseded_by': 'b'}, expected_version=2)
        item = self.app.agent.query_context()['superseded_topics'][0]
        self.assertEqual((item['decision_outcome'], item['superseded_by']), ('accepted', 'b'))

    def test_legacy_read_save_retry_restore_and_rebuild_do_not_invent_consent(self):
        for outcome in ('deferred', 'superseded'):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as tmp:
                self.app = DashboardServer(Config({'git_commit': {'enabled': False}}, Path(tmp)))
                self.svc = self.app.service
                raw = self.legacy(outcome)
                original = self.detail()['rounds']
                ctx = self.app.agent.query_context()
                self.assertEqual(ctx[outcome + '_topics'][0]['decision_outcome'], '')
                self.assertEqual((self.svc.config.decisions_dir / 'a.md').read_bytes(), raw)
                self.assertEqual(self.app.overview_from_topics(self.app.load_all_topics_meta())[0], [])
                data = {'new_agent_reply': 'Continue to wait'}
                with patch.object(self.svc.db, 'upsert_topic', side_effect=OSError('interrupted index')):
                    with self.assertRaises(OSError):
                        self.svc.save_topic('a', data, expected_version=1, request_id='legacy-save')
                receipt = self.svc.save_topic('a', data, expected_version=1, request_id='legacy-save')
                self.assertEqual((self.detail()['workflow_state'], self.detail()['decision_outcome']), (outcome, ''))
                self.assertEqual(len(self.detail()['rounds']), len(original) + 1)
                self.svc.restore_single_topic('a', receipt['prior_rev_id'], expected_version=2)
                self.assertEqual(self.detail()['decision_outcome'], outcome)
                self.assertEqual(self.detail()['rounds'][0]['user_opinion'], original[0]['user_opinion'])
                version = self.detail()['version']
                self.svc.save_topic('a', {'decision_outcome': 'accepted', 'new_user_opinion': 'I agree to this arrangement'}, expected_version=version)
                self.assertEqual((self.detail()['workflow_state'], self.detail()['decision_outcome']), (outcome, 'accepted'))
                self.svc.recovery.rebuild_index_from_markdown()
                self.assertTrue(self.svc.recovery.check_consistency()['consistent'])
                self.assertEqual(self.app.agent.query_context()[outcome + '_topics'][0]['decision_outcome'], 'accepted')

    def test_partial_acceptance_and_rejection_survive_progress_changes(self):
        self.create(decision_outcome='partially_accepted', new_user_opinion='Agree A, reserve B')
        self.svc.save_topic('a', {'workflow_state': 'deferred'}, expected_version=1)
        self.assertIn('部分同意', self.app.agent.format_as_markdown(self.app.agent.query_context()))
        self.svc.save_topic('a', {'decision_outcome': 'rejected', 'rejection_reason': 'A failed'}, expected_version=2)
        ctx = self.app.agent.query_context()
        self.assertEqual(ctx['deferred_topics'][0]['decision_outcome'], 'rejected')
        self.assertEqual(ctx['deferred_topics'][0]['rejection_reason'], 'A failed')
        self.assertIn('A failed', self.app.agent.format_as_markdown(ctx))
        self.svc.save_topic('a', {'workflow_state': 'superseded', 'superseded_by': 'b'}, expected_version=3)
        ctx = self.app.agent.query_context()
        self.assertEqual(ctx['rejected_proposals'], [])
        self.assertEqual(ctx['superseded_topics'][0]['decision_outcome'], 'rejected')
        self.assertTrue(self.svc.recovery.check_consistency()['consistent'])

    def test_decided_without_outcome_is_not_consent(self):
        self.create(workflow_state='decided', decision_outcome='')
        ctx = self.app.agent.query_context()
        self.assertEqual(ctx['active_decisions'], [])
        self.assertEqual(ctx['pending_requirements'][0]['decision_outcome'], '')
        self.assertEqual(self.app.overview_from_topics(self.app.load_all_topics_meta())[0], [])

    def test_amend_waiting_round_preserves_progress_and_history(self):
        self.create(workflow_state='deferred', decision_outcome='accepted', new_user_opinion='After milestone A')
        data = {'edit_latest_round': True, 'new_user_opinion': 'After milestone B\nKeep waiting'}
        receipt = self.svc.save_topic('a', data, expected_version=1, request_id='amend-wait')
        self.assertEqual(len(self.detail()['rounds']), 1)
        self.assertEqual(self.detail()['workflow_state'], 'deferred')
        self.svc.restore_single_topic('a', receipt['prior_rev_id'], expected_version=2)
        self.assertEqual(self.detail()['rounds'][0]['user_opinion'], 'After milestone A')
        self.assertEqual(self.detail()['decision_outcome'], 'accepted')
        self.assertTrue(self.svc.recovery.check_consistency()['consistent'])

    def test_invalid_states_stale_versions_and_conflicting_replays_still_fail(self):
        self.create()
        for data in ({'workflow_state': 'never'}, {'decision_outcome': 'maybe'},
                     {'workflow_state': 'never', 'decision_outcome': 'deferred'},
                     {'workflow_state': 'deferred', 'decision_outcome': 'partially_accepted'}):
            with self.assertRaises(TopicValidationError):
                self.svc.save_topic('a', data, expected_version=1)
        self.svc.save_topic('a', {'workflow_state': 'deferred'}, expected_version=1, request_id='wait')
        with self.assertRaises(VersionConflictError):
            self.svc.save_topic('a', {'workflow_state': 'decided'}, expected_version=1)
        with self.assertRaises(IdempotencyConflictError):
            self.svc.save_topic('a', {'workflow_state': 'decided'}, expected_version=1, request_id='wait')
        self.assertEqual(self.detail()['workflow_state'], 'deferred')
        self.assertTrue(self.svc.recovery.check_consistency()['consistent'])
