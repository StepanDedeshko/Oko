import unittest

from app.app_info import APP_VERSION
from app.zabbix_ack import extract_task_ack_comments, has_exact_task_ack_comment


class ZabbixAckTaskCommentTests(unittest.TestCase):
    def test_extract_redmine_task_comment(self):
        text = "История\nЗадача Redmine #12345: https://redmine.example/issues/12345\nГотово"
        self.assertEqual(extract_task_ack_comments(text), ["Задача Redmine #12345: https://redmine.example/issues/12345"])

    def test_extract_mm_task_comment(self):
        text = "Задача на ММ #123456: https://mm.example/tickets/123456"
        self.assertEqual(extract_task_ack_comments(text), ["Задача на ММ #123456: https://mm.example/tickets/123456"])

    def test_ignore_number_only_and_url_only_fragments(self):
        text = "#12345\nhttps://redmine.example/issues/12345\nЗадача Redmine #12345\nЗадача на ММ: https://mm.example/tickets/123456"
        self.assertEqual(extract_task_ack_comments(text), [])

    def test_deduplicate_identical_comments(self):
        text = "\n".join([
            "Задача Redmine #12345: https://redmine.example/issues/12345",
            "Задача Redmine #12345: https://redmine.example/issues/12345",
        ])
        self.assertEqual(extract_task_ack_comments(text), ["Задача Redmine #12345: https://redmine.example/issues/12345"])

    def test_multiple_different_comments_require_choice(self):
        text = "\n".join([
            "Задача Redmine #12345: https://redmine.example/issues/12345",
            "Задача на ММ #123456: https://mm.example/tickets/123456",
        ])
        self.assertEqual(len(extract_task_ack_comments(text)), 2)

    def test_existing_same_comment_is_skipped_and_not_duplicated(self):
        comment = "Задача на ММ #123456: https://mm.example/tickets/123456"
        text = f"До\n{comment}\nПосле"
        self.assertTrue(has_exact_task_ack_comment(text, comment))
        self.assertEqual(extract_task_ack_comments(text + "\n" + comment), [comment])

    def test_app_version_remains_unchanged(self):
        self.assertEqual(APP_VERSION, "0.3.1")


if __name__ == "__main__":
    unittest.main()
