import unittest


class DutyModeGuardImportTests(unittest.TestCase):
    def test_duty_flow_guard_is_available_in_duty_mode_module(self):
        try:
            import app.duty_mode as duty_mode
        except ImportError as exc:
            if "libGL.so.1" in str(exc):
                self.skipTest(f"Qt runtime dependency is unavailable: {exc}")
            raise

        self.assertTrue(hasattr(duty_mode, "DutyFlowGuard"))
        self.assertEqual(duty_mode.DutyFlowGuard.__name__, "DutyFlowGuard")


if __name__ == "__main__":
    unittest.main()
