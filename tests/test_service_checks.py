import json
import unittest

from app.config import build_settings_export, collect_exportable_settings
from app.service_checks import (
    AUTH_VISIBLE_HTML_FORM,
    build_auth_form_js,
    build_autofill_error_message,
    build_service_check_note_text,
    default_service_item,
    ensure_service_checks_defaults,
    evaluate_service_check_page,
    make_service_result,
    normalize_service_id,
    parse_text_markers,
    safe_autofill_script_preview,
    service_result_display_label,
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


    def test_auth_form_js_is_self_contained_and_vue_friendly(self):
        js = build_auth_form_js(
            {
                "login_selector": "input[type=text].el-input__inner",
                "password_selector": "#passw",
                "submit_selector": "button.login_btn",
            },
            {"login": "user", "password": "secret"},
        )
        self.assertIn("setNativeValue", js)
        self.assertIn("Object.getOwnPropertyDescriptor", js)
        self.assertIn("input", js)
        self.assertIn("change", js)
        self.assertIn("blur", js)
        self.assertIn("MouseEvent", js)
        self.assertIn("missing_form_elements", js)
        self.assertIn("autofill_failed", js)
        self.assertIn("document.readyState", js)
        self.assertIn("iframe_count", js)
        self.assertIn("text_input_count", js)
        stripped = js.strip()
        self.assertTrue(stripped)
        self.assertFalse(stripped.startswith(("'", '"')))
        self.assertFalse(stripped.endswith(("'", '"')))
        self.assertTrue(stripped.endswith(")()") or stripped.endswith(")();"))
        self.assertIn("return {", js)
        self.assertIn("ok: true", js)
        self.assertNotIn(".then", js)
        self.assertNotIn("new Promise", js)
        self.assertNotIn("async", js)
        self.assertNotIn("await", js)

    def test_autofill_script_preview_redacts_credentials(self):
        js = build_auth_form_js(
            {"login_selector": "#login", "password_selector": "#password", "submit_selector": "button"},
            {"login": "user@example.local", "password": "super-secret-password"},
        )
        head, tail = safe_autofill_script_preview(js, {"login": "user@example.local", "password": "super-secret-password"}, size=10000)
        preview = head + tail
        self.assertNotIn("user@example.local", preview)
        self.assertNotIn("super-secret-password", preview)
        self.assertIn("<redacted>", preview)

    def test_missing_selector_error_message_uses_selectors_only(self):
        service = {
            "login_selector": "input.login",
            "password_selector": "input.pass",
            "submit_selector": "button.submit",
        }
        message = build_autofill_error_message(
            service,
            {"ok": False, "error": "missing_form_elements", "missing": ["login", "submit"], "ready_state": "complete", "iframe_count": 1, "text_input_count": 2, "password_input_count": 1, "button_count": 3, "found_inputs": ["input[type=text].el-input__inner"], "found_buttons": ["button.login_btn"]},
        )
        self.assertIn("поле логина: input.login", message)
        self.assertIn("кнопка входа: button.submit", message)
        self.assertIn("document.readyState: complete", message)
        self.assertIn("iframe на странице: 1", message)
        self.assertIn("Найдены input: input[type=text].el-input__inner", message)
        self.assertIn("Найдены button: button.login_btn", message)
        self.assertNotIn("input.pass", message)
        self.assertNotIn("secret", message.lower())

    def test_invalid_js_result_has_safe_autofill_error(self):
        message = build_autofill_error_message({}, None)
        self.assertIn("JS автозаполнения не вернул результат", message)
        empty_message = build_autofill_error_message({}, "")
        self.assertIn("JS автозаполнения вернул пустую строку вместо объекта", empty_message)

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
        default_item = default_service_item("FacePay")
        self.assertFalse(default_item["allow_insecure_ssl"])
        self.assertTrue(default_item["visible_window_close_on_success"])
        self.assertFalse(default_item["visible_window_close_on_error"])
        self.assertEqual(default_item["visible_window_close_delay_seconds"], 3)
        item = default_service_item("FacePay")
        config["service_checks"]["items"].append(item)
        ensure_service_checks_defaults(config)
        self.assertEqual(config["service_checks"]["items"][0]["id"], "facepay")
        self.assertFalse(config["service_checks"]["items"][0]["allow_insecure_ssl"])
        self.assertTrue(config["service_checks"]["items"][0]["visible_window_close_on_success"])
        self.assertFalse(config["service_checks"]["items"][0]["visible_window_close_on_error"])
        self.assertEqual(config["service_checks"]["items"][0]["visible_window_close_delay_seconds"], 3)

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



    def test_manual_ok_error_and_skip_results_are_rendered_in_note(self):
        results = [
            make_service_result({"id": "a", "name": "FacePay"}, status="ok", manual=True, details="Результат подтверждён вручную дежурным."),
            make_service_result({"id": "b", "name": "Биометрик"}, status="error", manual=True, details="Ошибка подтверждена вручную дежурным."),
            make_service_result({"id": "c", "name": "Шар"}, status="unknown", manual=True, details="Проверка пропущена вручную."),
        ]
        text = build_service_check_note_text({}, results, checked_at="2026-06-10 13:30")
        self.assertIn("FacePay — ОК — подтверждено вручную", text)
        self.assertIn("Детали: Результат подтверждён вручную дежурным.", text)
        self.assertIn("Биометрик — Ошибка — подтверждена вручную", text)
        self.assertIn("Детали: Ошибка подтверждена вручную дежурным.", text)
        self.assertIn("Шар — Пропущено вручную", text)
        self.assertIn("Детали: Проверка пропущена вручную.", text)
        self.assertTrue(all(item["manual"] for item in results))
        self.assertEqual(service_result_display_label(results[0]), "ОК — подтверждено вручную")

    def test_visible_html_form_auth_type_is_preserved(self):
        config = {
            "service_checks": {
                "items": [{"id": "svc", "name": "Svc", "auth_type": AUTH_VISIBLE_HTML_FORM}]
            }
        }
        ensure_service_checks_defaults(config)
        item = config["service_checks"]["items"][0]
        self.assertEqual(item["auth_type"], AUTH_VISIBLE_HTML_FORM)

    def test_manual_required_note_contains_diagnostics_text(self):
        result = make_service_result(
            {"id": "svc", "name": "Сервис", "url": "https://internal.local"},
            status="manual_required",
            error="Окно проверки оставлено открытым для диагностики.",
        )
        text = build_service_check_note_text({}, [result], checked_at="2026-06-10 13:30")
        self.assertIn("Сервис — Требуется ручная проверка", text)
        self.assertIn("Окно проверки оставлено открытым для диагностики.", text)

    def test_export_includes_service_checks_but_not_credentials(self):
        config = {
            "service_checks": {
                "otrs_task_url": "https://otrs.local/note",
                "items": [{
                    "id": "facepay",
                    "name": "FacePay",
                    "enabled": True,
                    "url": "https://example.local",
                    "login_selector": "input[name=login]",
                    "password_selector": "input[type=password]",
                    "submit_selector": "button[type=submit]",
                    "allow_insecure_ssl": True,
                    "auth_type": "visible_html_form",
                    "visible_window_close_on_success": True,
                    "visible_window_close_on_error": False,
                    "visible_window_close_delay_seconds": 3,
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
        self.assertEqual(item["auth_type"], "visible_html_form")
        self.assertIn("login_selector", item)
        self.assertTrue(item["allow_insecure_ssl"])
        self.assertEqual(item["visible_window_close_delay_seconds"], 3)
        serialized = json.dumps(exported, ensure_ascii=False).lower()
        self.assertNotIn("must-not-export", serialized)
        self.assertNotIn('"login"', serialized)
        self.assertNotIn('"password"', serialized)


if __name__ == "__main__":
    unittest.main()
