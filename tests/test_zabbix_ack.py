from pathlib import Path
import unittest

from app.app_info import APP_VERSION
from app.zabbix_ack import (
    comment_already_present,
    deduplicate_ack_targets,
    extract_mm_otrs_reference,
    extract_redmine_reference,
    extract_task_ack_comments,
    mm_otrs_ack_comment,
    needs_acknowledgement,
    plan_zabbix_update,
    redmine_ack_comment,
    zabbix_acknowledgement_js,
)


class ZabbixAutomaticAcknowledgementTests(unittest.TestCase):
    def test_build_redmine_acknowledgement_comment(self):
        self.assertEqual(
            redmine_ack_comment("12345", "https://redmine.example/issues/12345"),
            "Задача Redmine #12345: https://redmine.example/issues/12345",
        )
        self.assertEqual(redmine_ack_comment("", "https://redmine.example/issues/12345"), "")
        self.assertEqual(redmine_ack_comment("12345", ""), "")

    def test_build_mm_otrs_acknowledgement_comment(self):
        self.assertEqual(
            mm_otrs_ack_comment("67890", "https://itsm.example/Ticket/67890"),
            "Задача на ММ #67890: https://itsm.example/Ticket/67890",
        )
        self.assertEqual(mm_otrs_ack_comment("67890", ""), "")
        self.assertEqual(mm_otrs_ack_comment("", "https://itsm.example/Ticket/67890"), "")

    def test_extract_task_ack_comments_from_zabbix_text(self):
        text = """История
Задача Redmine #12345: https://redmine.example/issues/12345
Задача на ММ #123456: https://itsm.example/Ticket/123456
"""
        self.assertEqual(
            extract_task_ack_comments(text),
            [
                "Задача Redmine #12345: https://redmine.example/issues/12345",
                "Задача на ММ #123456: https://itsm.example/Ticket/123456",
            ],
        )

    def test_extract_task_ack_comments_ignores_partial_fragments_and_deduplicates(self):
        text = """
        Задача Redmine #12345
        Задача Redmine: https://redmine.example/issues/12345
        Задача на ММ #123456
        Задача на ММ: https://itsm.example/Ticket/123456
        Задача Redmine #12345: https://redmine.example/issues/12345
        Задача Redmine #12345: https://redmine.example/issues/12345
        """
        self.assertEqual(extract_task_ack_comments(text), ["Задача Redmine #12345: https://redmine.example/issues/12345"])

    def test_multiple_different_task_comments_require_choice_dialog(self):
        comments = extract_task_ack_comments(
            "Задача Redmine #12345: https://redmine.example/issues/12345\n"
            "Задача на ММ #123456: https://itsm.example/Ticket/123456"
        )
        self.assertEqual(len(comments), 2)
        source = (Path(__file__).resolve().parents[1] / "app" / "live_zabbix_widget.py").read_text(encoding="utf-8")
        self.assertIn("QInputDialog.getItem", source)
        self.assertIn("Выберите комментарий задачи для копирования", source)

    def test_existing_same_comment_is_skipped_by_duplicate_result(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "live_zabbix_widget.py").read_text(encoding="utf-8")
        self.assertIn("elif duplicate and not ack_required:", source)
        self.assertIn("Комментарий Zabbix уже есть, пропуск", source)

    def test_idempotency_existing_comment_prevents_duplicate(self):
        existing = "История\nЗадача Redmine #12345: https://redmine.example/issues/12345\n"
        self.assertTrue(comment_already_present(existing, "Задача Redmine #12345: https://redmine.example/issues/12345"))
        self.assertFalse(comment_already_present(existing, "Задача Redmine #99999: https://redmine.example/issues/99999"))

    def test_deduplicate_selected_rows_by_ack_or_problem_url(self):
        items = [
            {"ack_url": "https://z/ack/1", "problem_url": "https://z/p/1", "host": "h1", "trigger_name": "t1", "ack_text": "Нет"},
            {"ack_url": "https://z/ack/1", "problem_url": "https://z/p/1", "host": "h1", "trigger_name": "t1", "ack_text": "Нет"},
            {"ack_url": "", "problem_url": "https://z/p/2", "host": "h2", "trigger_name": "t2", "ack_text": "Да"},
        ]
        targets = deduplicate_ack_targets(items)
        self.assertEqual([t.url for t in targets], ["https://z/ack/1", "https://z/p/2"])
        self.assertFalse(targets[0].already_acknowledged)
        self.assertTrue(targets[1].already_acknowledged)

    def test_logic_unacknowledged_requires_acknowledgement_and_comment(self):
        self.assertTrue(needs_acknowledgement({"ack_text": "Нет"}))
        plan = plan_zabbix_update({"ack_text": "Нет", "ack_url": "https://z/ack"}, "Задача Redmine #1")
        self.assertTrue(plan["ok"])
        self.assertTrue(plan["ack_required"])

    def test_logic_already_acknowledged_requires_comment_only(self):
        self.assertFalse(needs_acknowledgement({"ack_text": "Да"}))
        plan = plan_zabbix_update({"ack_text": "Да", "ack_url": "https://z/ack"}, "Задача на ММ #67890")
        self.assertTrue(plan["ok"])
        self.assertFalse(plan["ack_required"])

    def test_missing_task_reference_prevents_acknowledgement(self):
        plan = plan_zabbix_update({"ack_text": "Нет", "ack_url": "https://z/ack"}, "")
        self.assertFalse(plan["ok"])
        self.assertIn("задачи", plan["reason"])

    def test_missing_acknowledgement_url_produces_clear_failure(self):
        plan = plan_zabbix_update({"ack_text": "Нет"}, "Задача Redmine #12345")
        self.assertFalse(plan["ok"])
        self.assertIn("URL подтверждения Zabbix", plan["reason"])

    def test_reference_extraction(self):
        redmine_ref = extract_redmine_reference("Issue #12345", "https://redmine.example/projects/x/issues/new")
        self.assertEqual(redmine_ref["number"], "12345")
        self.assertEqual(redmine_ref["url"], "https://redmine.example/issues/12345")
        self.assertEqual(extract_mm_otrs_reference("Ticket# 202606301234", "")["number"], "202606301234")

    def test_js_contains_selector_fallbacks_and_markers(self):
        js = zabbix_acknowledgement_js("Задача Redmine #12345", True)
        for marker in ["message", "comment", "note", "Update", "Обновить", "Acknowledge", "Подтвердить", "Save", "Сохранить", "duplicate", "ack_required", "ack_touched", "submitted"]:
            self.assertIn(marker, js)
        self.assertNotIn("Да|Yes", js)

    def test_app_version_remains_unchanged(self):
        self.assertEqual(APP_VERSION, "0.3.1")
        self.assertIn('APP_VERSION = "0.3.1"', (Path(__file__).resolve().parents[1] / "app" / "app_info.py").read_text(encoding="utf-8"))

    def test_widget_has_task_creation_detection_integration_points(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "live_zabbix_widget.py").read_text(encoding="utf-8")
        self.assertIn("_open_redmine_creation_dialog", source)
        self.assertIn("_detect_redmine_created_issue", source)
        self.assertIn("_detect_mm_otrs_created_ticket", source)
        self.assertIn("Redmine issue detected", source)
        self.assertIn("MM/OTRS ticket detected", source)
        self.assertNotIn("QDesktopServices.openUrl(QUrl(redmine_url))", source)
        self.assertIn("Скопировать комментарий задачи на выбранные", source)
        self.assertIn("Ищу комментарии задач в выбранных проблемах", source)
        self.assertIn("Копирование комментария Zabbix", source)

    def test_widget_success_requires_zabbix_submit_or_duplicate(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "live_zabbix_widget.py").read_text(encoding="utf-8")
        self.assertIn("if submitted:", source)
        self.assertIn("elif duplicate and not ack_required:", source)
        self.assertIn("Комментарий Zabbix уже есть, пропуск", source)
        self.assertIn("комментарий уже есть, но подтверждение не отправлено", source)
        self.assertIn("submit не выполнен", source)
        self.assertNotIn("if '\"duplicate\":true' in text", source)


if __name__ == "__main__":
    unittest.main()
