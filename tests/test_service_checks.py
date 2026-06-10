import json
import unittest

from app.config import build_settings_export, collect_exportable_settings
from app.service_checks import (
    build_service_check_note_text,
    default_service_item,
    ensure_service_checks_defaults,
    evaluate_service_check_page,
    make_service_result,
    normalize_service_id,
    parse_text_markers,
    service_status_label,
    summarize_service_results,
)
from app.templates import (
    OTRS_SERVICE_CHECK_TEMPLATE_KEY,
    ensure_templates_defaults,
    get_otrs_service_check_template,
    render_template,
)


class ServiceChecksLogicTest(unittest.TestCase):
    def test_parse_text_markers_by_semicolon(self):
        self.assertEqual(parse_text_markers("Главная; Выход; ; Dashboard;выход"), ["Главная", "Выход", "Dashboard"])

    def test_normalize_service_id(self):
        self.assertEqual(normalize_service_id("Face Pay 2"), "face_pay_2")
        self.assertEqual(normalize_service_id("Шар"), "shar")

    def test_evaluate_ok_auth_error_unknown(self):
        service = {"success_texts": ["Главная", "Dashboard"], "error_texts": ["Access denied"]}
        self.assertEqual(evaluate_service_check_page(service, "Добро пожаловать. Главная", loaded=True)[0], "ok")
        status, _success, matched_error, error = evaluate_service_check_page(service, "Access denied", loaded=True)
        self.assertEqual(status, "auth_error")
        self.assertEqual(matched_error, "Access denied")
        self.assertIn("Access denied", error)
        self.assertEqual(evaluate_service_check_page(service, "plain page", loaded=True)[0], "unknown")

    def test_build_service_check_note_text_without_secret_fields(self):
        config = {}
        result = make_service_result(
            {"id": "facepay", "name": "FacePay", "url": "https://example.local"},
            status="auth_error",
            error="найден текст “Access denied”",
        )
        text = build_service_check_note_text(config, [result], checked_at="2026-06-10 13:30")
        self.assertIn("Проверка сервисов выполнена", text)
        self.assertIn("FacePay — Ошибка авторизации", text)
        self.assertIn("Access denied", text)
        self.assertNotIn("password", text.lower())
        self.assertNotIn("secret", text.lower())

    def test_service_template_variables_are_substituted(self):
        config = {}
        ensure_templates_defaults(config)
        template = get_otrs_service_check_template(config)
        rendered = render_template(template["text"], {
            "checked_at": "2026-06-10 13:30",
            "services_total_count": 1,
            "services_ok_count": 1,
            "services_error_count": 0,
            "services_timeout_count": 0,
            "services_unknown_count": 0,
            "services_results": "1. FacePay — ОК",
            "services_errors": "Не обнаружены",
        })
        self.assertNotIn("{services_results}", rendered)
        self.assertIn("1. FacePay — ОК", rendered)
        self.assertIn(OTRS_SERVICE_CHECK_TEMPLATE_KEY, config["templates"])

    def test_config_defaults_migration_adds_service_checks(self):
        config = {}
        settings = ensure_service_checks_defaults(config)
        self.assertIn("service_checks", config)
        self.assertEqual(settings["otrs_task_url"], "")
        self.assertFalse(default_service_item("FacePay")["allow_insecure_ssl"])
        item = default_service_item("FacePay")
        config["service_checks"]["items"].append(item)
        ensure_service_checks_defaults(config)
        self.assertEqual(config["service_checks"]["items"][0]["id"], "facepay")
        self.assertFalse(config["service_checks"]["items"][0]["allow_insecure_ssl"])

    def test_ssl_error_status_is_error_and_has_label(self):
        result = make_service_result({"id": "svc", "name": "Svc"}, status="ssl_error")
        stats = summarize_service_results([result])
        self.assertEqual(stats["errors"], 1)
        self.assertEqual(service_status_label("ssl_error"), "Ошибка SSL-сертификата")

    def test_ssl_error_note_contains_clear_error(self):
        result = make_service_result(
            {"id": "svc", "name": "Сервис", "url": "https://internal.local"},
            status="ssl_error",
            error="Ошибка SSL-сертификата: проверьте сертификат сервиса",
        )
        text = build_service_check_note_text({}, [result], checked_at="2026-06-10 13:30")
        self.assertIn("Сервис — Ошибка SSL-сертификата", text)
        self.assertIn("Ошибка SSL-сертификата: проверьте сертификат сервиса", text)
        self.assertIn("https://internal.local", text)

    def test_ssl_warning_note_contains_warning_for_ok_result(self):
        result = make_service_result(
            {"id": "svc", "name": "Сервис", "url": "https://internal.local"},
            status="ok",
            warning="SSL-сертификат был принят как внутренний/самоподписанный.",
        )
        text = build_service_check_note_text({}, [result], checked_at="2026-06-10 13:30")
        self.assertIn("Сервис — ОК", text)
        self.assertIn("Предупреждение: SSL-сертификат был принят как внутренний/самоподписанный.", text)

    def test_export_includes_service_checks_but_not_credentials(self):
        config = {
            "service_checks": {
                "otrs_task_url": "https://otrs.local/note",
                "items": [{
                    "id": "facepay",
                    "name": "FacePay",
                    "enabled": True,
                    "url": "https://example.local",
                    "auth_type": "html_form",
                    "login_selector": "input[name=login]",
                    "password_selector": "input[type=password]",
                    "submit_selector": "button[type=submit]",
                    "allow_insecure_ssl": True,
                    "success_texts": ["Главная"],
                    "error_texts": ["Access denied"],
                    "login": "must-not-export",
                    "password": "must-not-export",
                }],
            }
        }
        exported = build_settings_export(config)
        self.assertIn("service_checks", exported["settings"])
        item = exported["settings"]["service_checks"]["items"][0]
        self.assertEqual(item["auth_type"], "html_form")
        self.assertIn("login_selector", item)
        self.assertTrue(item["allow_insecure_ssl"])
        serialized = json.dumps(exported, ensure_ascii=False).lower()
        self.assertNotIn("must-not-export", serialized)
        self.assertNotIn('"login"', serialized)
        self.assertNotIn('"password"', serialized)


if __name__ == "__main__":
    unittest.main()
