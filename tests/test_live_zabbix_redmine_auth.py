import unittest
from pathlib import Path

from app.app_info import APP_VERSION
from app.live_zabbix import DEFAULT_REDMINE_LOGIN_URL, default_live_monitor_config
from app.templates import default_redmine_special_task_template, default_redmine_task_template


class LiveZabbixRedmineAuthTests(unittest.TestCase):
    def setUp(self):
        self.repo = Path(__file__).resolve().parents[1]
        self.widget_source = (self.repo / "app" / "live_zabbix_widget.py").read_text(encoding="utf-8")
        self.profile_source = (self.repo / "app" / "home_config.py").read_text(encoding="utf-8")
        self.duty_settings_source = (self.repo / "app" / "duty_settings.py").read_text(encoding="utf-8")

    def test_redmine_login_url_default_exists(self):
        self.assertEqual(
            DEFAULT_REDMINE_LOGIN_URL,
            "https://redmine.stdpr.ru/login?back_url=https%3A%2F%2Fredmine.stdpr.ru%2Fprojects",
        )
        self.assertEqual(default_live_monitor_config()["redmine_login_url"], DEFAULT_REDMINE_LOGIN_URL)
        self.assertIn("add_section_title(\"Redmine\")", self.profile_source)
        self.assertIn("Сохранять логин и пароль Redmine", self.profile_source)

    def test_redmine_credentials_are_mainly_in_profile_not_duty_mode(self):
        self.assertIn("redmine_login_url_input", self.profile_source)
        self.assertIn("redmine_username_input", self.profile_source)
        self.assertIn("redmine_password_input", self.profile_source)
        self.assertIn('redmine_settings["redmine_login_url"]', self.profile_source)
        self.assertIn('redmine_settings["redmine_username"]', self.profile_source)
        self.assertIn('redmine_settings["redmine_password"]', self.profile_source)
        self.assertNotIn("redmine_password_input", self.duty_settings_source)

    def test_redmine_login_form_selectors_are_present_in_js(self):
        for selector in [
            'input#username, input[name="username"]',
            'input#password, input[name="password"]',
            'input#login-submit, input[name="login"], input[type="submit"]',
            "dispatchEvent(new Event('input'",
            "dispatchEvent(new Event('change'",
            "submitInput.click()",
        ]:
            self.assertIn(selector, self.widget_source)

    def test_saved_credentials_are_not_logged(self):
        self.assertNotIn("redmine_username=%s", self.widget_source)
        self.assertNotIn("redmine_password=%s", self.widget_source)
        self.assertNotIn("Redmine username saved", self.profile_source)
        self.assertNotIn("Redmine password saved", self.profile_source)

    def test_redmine_dialogs_are_compact_and_webview_gets_space(self):
        self.assertIn("self.resize(900, 650)", self.widget_source)
        self.assertIn("self.resize(1100, 760)", self.widget_source)
        self.assertIn("self.status_label.setMaximumHeight(44)", self.widget_source)
        self.assertIn("self.status_label.setMaximumHeight(28)", self.widget_source)
        self.assertIn("layout.addWidget(self.view, stretch=1)", self.widget_source)
        self.assertIn("self.status_label.setVisible(False)", self.widget_source)

    def test_broken_nginx_page_routes_to_redmine_auth_dialog(self):
        for marker in ["default error page for nginx", "/usr/share/nginx/html/50x.html", "Red Hat Enterprise Linux"]:
            self.assertIn(marker, self.widget_source)
        self.assertIn("payload.get(\"login_required\") or payload.get(\"broken\")", self.widget_source)
        self.assertIn("_open_redmine_auth_dialog", self.widget_source)
        self.assertIn("Авторизация Redmine", self.widget_source)

    def test_redmine_action_logs_status_at_start_and_no_selection_message(self):
        self.assertIn('self.poll_status_label.setText("Готовлю задачу Redmine...")', self.widget_source)
        self.assertIn('self.logger.info("Redmine action clicked")', self.widget_source)
        self.assertIn('self.logger.info("Redmine selected rows: count=%s"', self.widget_source)
        self.assertIn("Выберите строку проблемы Live Zabbix Monitor для создания задачи Redmine.", self.widget_source)
        self.assertIn("Redmine action stopped: no selected problem rows", self.widget_source)

    def test_redmine_graph_lookup_timeout_continues_to_redmine(self):
        self.assertIn("_redmine_graph_lookup_timeout_ms = 9000", self.widget_source)
        self.assertIn("_on_redmine_graph_lookup_timeout", self.widget_source)
        self.assertIn("Redmine graph lookup timeout; continuing without graph link", self.widget_source)
        self.assertIn("Ссылка на график не найдена, продолжаю создание Redmine...", self.widget_source)
        self.assertIn("self._load_next_redmine_graph_lookup()", self.widget_source)

    def test_redmine_ip_lookup_timeout_continues_to_redmine(self):
        self.assertIn("_redmine_ip_lookup_timeout_ms = 9000", self.widget_source)
        self.assertIn("_on_redmine_ip_lookup_timeout", self.widget_source)
        self.assertIn("Redmine IP lookup timeout; continuing without IP", self.widget_source)
        self.assertIn("IP не найден, продолжаю создание Redmine...", self.widget_source)
        self.assertIn("self._load_next_redmine_ip_lookup()", self.widget_source)

    def test_redmine_preparation_exceptions_are_logged_and_shown(self):
        self.assertIn("def _handle_redmine_preparation_error", self.widget_source)
        self.assertIn('self.logger.exception("Redmine preparation failed")', self.widget_source)
        self.assertIn("Ошибка подготовки задачи Redmine. Подробности записаны в лог.", self.widget_source)
        self.assertIn("except Exception:", self.widget_source)

    def test_redmine_dialog_open_path_cannot_silently_stop_after_enrichment(self):
        for marker in [
            "Redmine graph lookup finished/skipped; starting IP lookup",
            "Redmine IP lookup finished/skipped; URL build started",
            "Redmine URL diagnostics:",
            "field_names=%s",
            "Redmine dialog opening",
            "Redmine dialog opened",
            "Окно Redmine открыто",
        ]:
            self.assertIn(marker, self.widget_source)

    def test_login_success_reopens_original_redmine_create_url(self):
        self.assertIn("path.indexOf('/login') === -1", self.widget_source)
        self.assertIn("!hasLoginForm", self.widget_source)
        self.assertIn("self.success_callback(self.original_create_url)", self.widget_source)
        self.assertIn("self.view.load(QUrl(original_create_url))", self.widget_source)

    def test_issue_form_guard_requires_subject_description_and_new_issue_path(self):
        self.assertIn('document.querySelector(\'input[name="issue[subject]"]\')', self.widget_source)
        self.assertIn('document.querySelector(\'textarea[name="issue[description]"]\')', self.widget_source)
        self.assertIn("path.indexOf('/issues/new') !== -1", self.widget_source)
        self.assertIn("hasSubject && hasDescription && hasIssuePath", self.widget_source)
        self.assertIn("Redmine не открыл форму создания задачи", self.widget_source)

    def test_custom_field_94_default_is_not_applicable(self):
        self.assertEqual(default_redmine_task_template()["custom_field_94"], "Не применим")
        self.assertEqual(default_redmine_special_task_template()["custom_field_94"], "Не применим")
        self.assertIn('issue[custom_field_values][94]', self.widget_source)
        self.assertIn('or "Не применим"', self.widget_source)

    def test_app_version_remains_unchanged(self):
        self.assertEqual(APP_VERSION, "0.3.1")


if __name__ == "__main__":
    unittest.main()
