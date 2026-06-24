import unittest


class _Logger:
    def info(self, *args, **kwargs):
        pass

    def exception(self, *args, **kwargs):
        pass


class GraphTriggerCancelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import app.duty_mode as duty_mode
        except ImportError as exc:
            if "libGL.so.1" in str(exc):
                raise unittest.SkipTest(f"Qt runtime dependency is unavailable: {exc}")
            raise
        cls.duty_mode = duty_mode

    def make_widget_stub(self):
        widget = self.duty_mode.DutyModeWidget.__new__(self.duty_mode.DutyModeWidget)
        widget.logger = _Logger()
        widget._graph_trigger_check_id = 10
        widget.graph_trigger_check_started_for_overlay = True
        widget.duty_trigger_running = True
        widget.duty_trigger_queue = [{"id": "trigger-1"}]
        widget._duty_trigger_run_id = 1
        widget._duty_trigger_stage_id = 2
        widget._hidden_trigger_contexts = [{"id": "ctx-1"}]
        widget.hidden_trigger_views = [object()]
        widget._cleanup_hidden_view = lambda context: context.update({"cleanup_called": True})
        return widget

    def test_cancel_graph_trigger_check_invalidates_token_and_clears_state(self):
        widget = self.make_widget_stub()

        widget._cancel_graph_trigger_check("unit-test")

        self.assertEqual(widget._graph_trigger_check_id, 11)
        self.assertFalse(widget.duty_trigger_running)
        self.assertFalse(widget.graph_trigger_check_started_for_overlay)
        self.assertEqual(widget.duty_trigger_queue, [])
        self.assertIsNone(widget._duty_trigger_run_id)
        self.assertIsNone(widget._duty_trigger_stage_id)
        self.assertTrue(widget._hidden_trigger_contexts[0]["cancelled"])
        self.assertTrue(widget._hidden_trigger_contexts[0]["completed"])
        self.assertTrue(widget._hidden_trigger_contexts[0]["cleanup_called"])

    def test_stale_graph_trigger_callback_is_rejected_after_cancel(self):
        widget = self.make_widget_stub()
        old_id = widget._graph_trigger_check_id

        widget._cancel_graph_trigger_check("unit-test")

        self.assertFalse(widget._graph_trigger_callback_is_current(old_id, "callback"))
        self.assertTrue(widget._graph_trigger_callback_is_current(widget._graph_trigger_check_id, "callback"))

    def test_graph_overlay_close_cancels_flow_and_marks_graphs_skipped(self):
        widget = self.make_widget_stub()
        calls = []
        widget.graph_check_overlay = object()
        widget.duty_flow_running = True
        widget.duty_current_stage = "zabbix_graphs"
        widget._duty_stage_action_in_progress = False
        widget._duty_callback_is_current = lambda run_id, stage_id, callback="": True
        widget._cancel_graph_trigger_check = lambda reason="": calls.append(("cancel_triggers", reason))
        widget.update_dashboard_summary = lambda: calls.append(("update", ""))

        def cancel_flow(reason=""):
            widget.duty_flow_running = False
            calls.append(("cancel_flow", reason))

        widget._cancel_current_duty_flow = cancel_flow

        widget._graph_overlay_closed(run_id=1, stage_id=2)

        self.assertIsNone(widget.graph_check_overlay)
        self.assertFalse(widget.duty_flow_running)
        self.assertEqual(widget.duty_zabbix_graphs_status, "Пропущено")
        self.assertEqual(widget.duty_zabbix_status, "пропущено")
        self.assertIn(("cancel_triggers", "graph overlay closed by user"), calls)
        self.assertIn(("cancel_flow", "graph overlay closed by user"), calls)


if __name__ == "__main__":
    unittest.main()
