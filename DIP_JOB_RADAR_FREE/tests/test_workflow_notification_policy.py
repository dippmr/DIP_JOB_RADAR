"""Guard against reintroducing per-scan Telegram summary messages."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / '.github' / 'workflows' / 'main.yml'


class TestWorkflowNotificationPolicy(unittest.TestCase):
    def setUp(self):
        self.workflow = WORKFLOW.read_text(encoding='utf-8')

    def test_monitor_is_called_in_real_workflow(self):
        self.assertIn('run: python -m radar.smart_notifications', self.workflow)
        self.assertIn('RADAR_WORKFLOW_STATUS: ${{ job.status }}', self.workflow)
        self.assertIn('RADAR_SCAN_STATUS: ${{ steps.radar_scan.outcome }}', self.workflow)

    def test_run_by_run_telegram_success_messages_are_removed(self):
        self.assertNotIn('Notify Telegram after every run', self.workflow)
        self.assertNotIn('Telegram notification sent', self.workflow)
        self.assertIn("SEND_HEARTBEAT: '0'", self.workflow)
        self.assertIn("WEEKLY_REPORT: '0'", self.workflow)
        self.assertIn("SEND_FEED_ALERT: '0'", self.workflow)

    def test_monitor_state_is_committed_for_daily_deduplication(self):
        self.assertIn('git add DIP_JOB_RADAR_FREE/data/monitor_state.json', self.workflow)
        self.assertIn("steps.checkout.outcome == 'success'", self.workflow)

    def test_external_dispatch_remains_the_only_trigger(self):
        self.assertIn('workflow_dispatch:', self.workflow)
        self.assertNotIn('    - cron:', self.workflow)


if __name__ == '__main__':
    unittest.main()
