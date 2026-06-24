import unittest

from app.duty_flow_guard import DutyFlowGuard


class DutyFlowGuardTests(unittest.TestCase):
    def test_duplicate_start_is_ignored_while_running(self):
        guard = DutyFlowGuard()
        first = guard.start_flow()
        second = guard.start_flow()
        self.assertEqual(first, 1)
        self.assertIsNone(second)
        self.assertTrue(guard.running)

    def test_cancel_is_idempotent_and_resets_running(self):
        guard = DutyFlowGuard()
        guard.start_flow()
        guard.cancel_flow("test")
        guard.cancel_flow("again")
        self.assertFalse(guard.running)
        self.assertFalse(guard.stage_action_in_progress)

    def test_stage_action_duplicate_and_reset_on_next_stage(self):
        guard = DutyFlowGuard()
        guard.start_flow()
        guard.start_stage("services")
        self.assertTrue(guard.start_action("skip"))
        self.assertFalse(guard.start_action("skip"))
        guard.start_stage("zabbix_problems")
        self.assertFalse(guard.stage_action_in_progress)
        self.assertTrue(guard.start_action("skip"))

    def test_stale_callbacks_are_rejected(self):
        guard = DutyFlowGuard()
        guard.start_flow()
        token = guard.start_stage("zabbix_problems")
        guard.start_stage("zabbix_graphs")
        self.assertFalse(guard.is_current(token.run_id, token.stage_id, callback="old_stage"))
        current = guard.token()
        self.assertTrue(guard.is_current(current.run_id, current.stage_id, callback="current"))
        guard.cancel_flow("done")
        self.assertFalse(guard.is_current(current.run_id, current.stage_id, callback="old_run"))

    def test_finish_resets_running(self):
        guard = DutyFlowGuard()
        guard.start_flow()
        guard.start_stage("zabbix_note")
        guard.finish_flow()
        self.assertFalse(guard.running)
        self.assertFalse(guard.stage_action_in_progress)


if __name__ == "__main__":
    unittest.main()
