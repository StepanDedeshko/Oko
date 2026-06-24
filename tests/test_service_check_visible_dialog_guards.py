import unittest


class _Logger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass


class ServiceCheckVisibleDialogGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import app.duty_mode as duty_mode
        except ImportError as exc:
            if "libGL.so.1" in str(exc):
                raise unittest.SkipTest(f"Qt runtime dependency is unavailable: {exc}")
            raise
        cls.duty_mode = duty_mode

    def make_dialog_stub(self):
        dialog = self.duty_mode.ServiceCheckVisibleDialog.__new__(self.duty_mode.ServiceCheckVisibleDialog)
        dialog.service = {"id": "svc-1", "name": "Service 1"}
        dialog.logger = _Logger()
        dialog.finished = False
        dialog.state = "result_check"
        dialog._closed = False
        dialog._cancelled = False
        dialog._cleaned_up = False
        dialog._check_generation = 1
        dialog.page = None
        return dialog

    def test_read_page_text_ignores_missing_page(self):
        dialog = self.make_dialog_stub()

        dialog.read_page_text()

        self.assertFalse(dialog.finished)

    def test_callback_after_close_is_ignored(self):
        dialog = self.make_dialog_stub()
        dialog._closed = True

        self.assertFalse(dialog.callback_allowed("read_page_text", {"result_check"}))

    def test_run_page_js_ignores_stale_generation_callback(self):
        dialog = self.make_dialog_stub()
        calls = []

        class Page:
            def runJavaScript(self, _script, callback):
                dialog._check_generation += 1
                callback("result")

        dialog.page = Page()

        result = dialog._run_page_js("1 + 1", calls.append, "test_js")

        self.assertTrue(result)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
