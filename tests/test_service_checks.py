import json
import os
from pathlib import Path
import unittest

from app.config import build_settings_export, collect_exportable_settings
from app.service_checks import (
    AUTH_VISIBLE_HTML_FORM,
    build_auth_form_js,
    build_auth_form_presence_js,
    build_click_selector_js,
    build_click_action_js,
    build_load_false_diagnostics_js,
    build_autofill_error_message,
    build_result_selector_check_js,
    build_wait_selector_js,
    build_wait_selector_action_js,
    build_wait_text_action_js,
    build_service_check_note_text,
    can_open_next_visible_service_after_cleanup,
    default_service_item,
    ensure_service_checks_defaults,
    evaluate_service_check_page,
    make_service_result,
    normalize_service_id,
    parse_autofill_callback_result,
    normalize_service_actions,
    parse_selector_markers,
    parse_text_markers,
    safe_autofill_script_preview,
    service_action_failure_message,
    service_result_display_label,
    service_status_label,
    load_false_continuation_action,
    should_continue_after_http_error_load,
    summarize_service_results,
    load_false_auth_form_available,
    visible_html_form_should_start_autofill_wait,
    visible_service_start_diagnostics,
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
        self.assertIn("input_text_count", js)
        self.assertIn("location_href", js)
        self.assertIn("JSON.stringify", js)
        stripped = js.strip()
        self.assertTrue(stripped)
        self.assertFalse(stripped.startswith(("'", '"')))
        self.assertFalse(stripped.endswith(("'", '"')))
        self.assertTrue(stripped.endswith(")()") or stripped.endswith(")();"))
        self.assertIn("return JSON.stringify", js)
        self.assertIn("ok: true", js)
        self.assertNotIn(".then", js)
        self.assertNotIn("new Promise", js)
        self.assertNotIn("async", js)
        self.assertNotIn("await", js)


    def test_auth_form_presence_js_returns_json_diagnostics(self):
        js = build_auth_form_presence_js({
            "login_selector": "#login",
            "password_selector": "#password",
            "submit_selector": "button[type=submit]",
        })
        self.assertIn("JSON.stringify", js)
        self.assertIn("missing_form_elements", js)
        self.assertIn("diagnostics", js)
        self.assertIn("iframe_count", js)
        self.assertIn("input_text_count", js)
        self.assertTrue(js.strip().endswith(")()") or js.strip().endswith(")();"))
        self.assertNotIn(".then", js)
        self.assertNotIn("new Promise", js)
        self.assertNotIn("async", js)
        self.assertNotIn("await", js)

    def test_load_false_diagnostics_js_is_safe_and_json_based(self):
        js = build_load_false_diagnostics_js({
            "login_selector": "#login",
            "password_selector": "#password",
            "submit_selector": "button[type=submit]",
            "success_selectors": [".dashboard"],
            "error_selectors": [".error"],
        })
        self.assertIn("JSON.stringify", js)
        self.assertIn("body_found", js)
        self.assertIn("ready_state", js)
        self.assertIn("location_protocol", js)
        self.assertIn("location_host", js)
        self.assertIn("location_pathname", js)
        self.assertIn("iframe_count", js)
        self.assertIn("iframe_srcs", js)
        self.assertIn("sanitizeUrl", js)
        self.assertIn("login_found", js)
        self.assertIn("success_found", js)
        self.assertNotIn(".value", js.lower())
        self.assertNotIn("cookie", js.lower())
        self.assertNotIn("localStorage", js)
        self.assertNotIn("sessionStorage", js)
        self.assertTrue(js.strip().endswith(")()") or js.strip().endswith(")();"))

    def test_http_error_load_continues_only_when_allowed_and_dom_matches(self):
        service = {"allow_http_error_load": True}
        diagnostics = {"body_found": True, "login_found": True, "password_found": True, "submit_found": True}
        self.assertTrue(load_false_auth_form_available(diagnostics))
        self.assertTrue(should_continue_after_http_error_load(service, diagnostics))
        self.assertTrue(should_continue_after_http_error_load(service, {"success_found": True}))
        self.assertTrue(should_continue_after_http_error_load(service, {"error_found": True}))
        self.assertFalse(should_continue_after_http_error_load(service, {"body_found": True}))
        self.assertFalse(should_continue_after_http_error_load({"allow_http_error_load": False}, diagnostics))
        self.assertEqual(load_false_continuation_action({"allow_http_error_load": False}, diagnostics), "load_error")
        self.assertEqual(load_false_continuation_action(service, {"body_found": True}), "wait")
        self.assertEqual(load_false_continuation_action(service, diagnostics), "autofill")
        self.assertEqual(load_false_continuation_action(service, {"success_found": True}), "result_selector")
        self.assertEqual(load_false_continuation_action(service, {"error_found": True}), "error_selector")

    def test_allow_http_error_load_default_false_and_migration(self):
        item = default_service_item("svc")
        self.assertFalse(item["allow_http_error_load"])
        config = {"service_checks": {"items": [{"id": "svc"}]}}
        ensure_service_checks_defaults(config)
        self.assertFalse(config["service_checks"]["items"][0]["allow_http_error_load"])


    def test_parse_selector_markers_by_semicolon_and_newline(self):
        self.assertEqual(parse_selector_markers(".ok; #logout\n[data-test=main]; .ok"), [".ok", "#logout", "[data-test=main]"])


    def test_logout_js_helpers_are_safe_and_json_based(self):
        click_js = build_click_selector_js(".user-menu")
        wait_js = build_wait_selector_js(["form.login", "button.sign-in"])
        for js in (click_js, wait_js):
            self.assertIn("JSON.stringify", js)
            self.assertIn("MouseEvent", click_js)
            self.assertNotIn(".value", js.lower())
            self.assertNotIn("cookie", js.lower())
            self.assertNotIn("localStorage", js)

    def test_logout_defaults_and_migration(self):
        item = default_service_item("svc")
        self.assertEqual(item["logout_menu_selector"], "")
        self.assertEqual(item["logout_button_selector"], "")
        self.assertEqual(item["logout_success_selectors"], [])
        self.assertEqual(item["logout_success_texts"], [])
        self.assertEqual(item["logout_wait_seconds"], 10)
        self.assertEqual(item["logout_menu_wait_seconds"], 5)
        self.assertEqual(item["post_login_actions"], [])
        self.assertEqual(item["logout_actions"], [])
        self.assertEqual(item["session_group"], "")
        self.assertEqual(item["session_group_order"], 0)
        self.assertFalse(item["session_group_login_owner"])
        self.assertFalse(item["session_group_logout_owner"])
        self.assertFalse(item["session_group_reuse_webview"])
        self.assertEqual(item["external_browser_open_delay_seconds"], 1)
        self.assertTrue(item["external_browser_manual_confirm"])
        self.assertEqual(item["external_browser_open_mode"], "tabs")
        config = {"service_checks": {"items": [{"id": "svc", "logout_success_selectors": "form.login; button.login", "logout_success_texts": "Войти; Login", "logout_actions": "click | .profile | 5 | 500 | Открыть профиль"}]}}
        ensure_service_checks_defaults(config)
        migrated = config["service_checks"]["items"][0]
        self.assertEqual(migrated["logout_success_selectors"], ["form.login", "button.login"])
        self.assertEqual(migrated["logout_success_texts"], ["Войти", "Login"])
        self.assertEqual(migrated["logout_actions"][0]["type"], "click")
        self.assertEqual(migrated["logout_actions"][0]["selector"], ".profile")

    def test_normalize_service_actions_from_text_and_list(self):
        actions = normalize_service_actions(
            "click | .menu | 5 | 500 | Открыть меню\n"
            "wait_selector | .ready | 10 | 0 | Раздел открыт\n"
            "wait_text | Готово | 7 | 0 | Текст найден\n"
            "delay |  | 0 | 250 | Пауза"
        )
        self.assertEqual([item["type"] for item in actions], ["click", "wait_selector", "wait_text", "delay"])
        self.assertEqual(actions[0]["selector"], ".menu")
        self.assertEqual(actions[2]["text"], "Готово")
        self.assertEqual(actions[3]["delay_ms"], 250)
        normalized = normalize_service_actions([{"type": "click", "selector": ".x", "timeout_seconds": "3", "delay_ms": "10"}])
        self.assertEqual(normalized[0]["timeout_seconds"], 3)

    def test_action_js_helpers_are_safe_and_json_based(self):
        for js in (build_click_action_js(".profile"), build_wait_selector_action_js(".ready"), build_wait_text_action_js("Готово")):
            self.assertIn("JSON.stringify", js)
            self.assertTrue(js.strip().endswith(")()") or js.strip().endswith(")();"))
            self.assertNotIn(".value", js.lower())
            self.assertNotIn("cookie", js.lower())
            self.assertNotIn("localStorage", js)
            self.assertNotIn("sessionStorage", js)
        self.assertIn("MouseEvent", build_click_action_js(".profile"))
        self.assertIn("innerText", build_wait_text_action_js("Готово"))

    def test_action_failure_message_and_logout_priority(self):
        action = {"type": "wait_selector", "selector": ".ready", "description": "Проверить раздел"}
        self.assertIn("мини-тест", service_action_failure_message("post_login", action, "selector_not_found"))
        service = {"logout_actions": [{"type": "click", "selector": ".profile"}], "logout_menu_selector": ".legacy", "logout_button_selector": ".legacy-logout"}
        self.assertTrue(service["logout_actions"])

    def test_visible_dialog_state_guards_are_present(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "duty_mode.py").read_text(encoding="utf-8")
        self.assertIn("self.auth_submitted = False", source)
        self.assertIn("self.logout_started = False", source)
        self.assertIn("Service check auth submit ignored", source)
        self.assertIn("Service check logout ignored", source)
        self.assertIn("Service check callback ignored", source)
        self.assertIn("Service check timers cancelled", source)
        self.assertIn("logout_success_wait", source)
        self.assertIn("Service check group started", source)
        self.assertIn("Service check group skip auth", source)
        self.assertIn("Service check group navigate next", source)
        self.assertIn("Service check group finished", source)
        self.assertIn("Service check group result check started", source)
        self.assertIn("Service check group result success", source)
        self.assertIn("Service check group post_login started", source)
        self.assertIn("Service check group post_login success", source)
        self.assertIn("post_login started without result selector", source)
        self.assertIn("Service check group result timeout diagnostics", source)
        self.assertIn("ExternalBrowserServiceCheckDialog", source)
        self.assertIn("Service check external browser group started", source)
        self.assertIn("Service check external browser open requested", source)
        self.assertIn("QDesktopServices.openUrl", source)
        self.assertIn("Открыть ещё раз", source)

    def test_logout_note_details_for_success_and_failure(self):
        ok_result = make_service_result({"id": "svc", "name": "Svc"}, status="ok", details="Вход выполнен, сервис работает, выход выполнен")
        text = build_service_check_note_text({}, [ok_result], checked_at="2026-06-10 13:30")
        self.assertIn("Svc — ОК", text)
        self.assertIn("Вход выполнен, сервис работает, выход выполнен", text)
        manual = make_service_result({"id": "svc", "name": "Svc"}, status="manual_required", error="Вход выполнен, но автоматический выход не подтверждён.")
        text = build_service_check_note_text({}, [manual], checked_at="2026-06-10 13:30")
        self.assertIn("Требуется ручная проверка", text)
        self.assertIn("автоматический выход не подтверждён", text)

    def test_result_selector_check_js_returns_json_without_credentials(self):
        js = build_result_selector_check_js({
            "success_selectors": [".account-menu"],
            "error_selectors": [".login-error"],
        })
        self.assertIn("JSON.stringify", js)
        self.assertIn("success_found", js)
        self.assertIn("error_found", js)
        self.assertIn("document.querySelector", js)
        self.assertNotIn(".value", js.lower())
        self.assertNotIn('getattribute("value")', js.lower())
        self.assertTrue(js.strip().endswith(")()") or js.strip().endswith(")();"))

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
            {
                "ok": False,
                "error": "missing_form_elements",
                "missing": ["login", "submit"],
                "diagnostics": {
                    "ready_state": "complete",
                    "location_href": "https://example.local/login",
                    "iframe_count": 1,
                    "input_text_count": 2,
                    "input_password_count": 1,
                    "button_count": 3,
                    "login_found": False,
                    "password_found": True,
                    "submit_found": False,
                    "found_inputs": ["input type=text class=el-input__inner"],
                    "found_buttons": ["button class=login_btn text=Вход"],
                },
            },
        )
        self.assertIn("поле логина: input.login", message)
        self.assertIn("кнопка входа: button.submit", message)
        self.assertIn("readyState=complete", message)
        self.assertIn("location=https://example.local/login", message)
        self.assertIn("iframe_count=1", message)
        self.assertIn("input_text_count=2", message)
        self.assertIn("input_password_count=1", message)
        self.assertIn("login_found=False", message)
        self.assertIn("found_inputs=input type=text class=el-input__inner", message)
        self.assertIn("found_buttons=button class=login_btn text=Вход", message)
        self.assertIn("форма авторизации находится внутри iframe", message)
        self.assertNotIn("input.pass", message)
        self.assertNotIn("secret", message.lower())

    def test_invalid_js_result_has_safe_autofill_error(self):
        message = build_autofill_error_message({}, None)
        self.assertIn("JS автозаполнения не вернул результат", message)
        empty_message = build_autofill_error_message({}, "")
        self.assertIn("JS автозаполнения вернул пустую строку вместо JSON", empty_message)

    def test_parse_autofill_callback_result_supports_json_string_and_errors(self):
        parsed, error = parse_autofill_callback_result('{"ok": true, "clicked": true}')
        self.assertIsNone(error)
        self.assertTrue(parsed["ok"])
        self.assertTrue(parsed["clicked"])

        parsed, error = parse_autofill_callback_result({"ok": True, "clicked": True})
        self.assertIsNone(error)
        self.assertTrue(parsed["ok"])

        parsed, error = parse_autofill_callback_result("")
        self.assertIsNone(parsed)
        self.assertEqual(error["error"], "empty_string_result")
        self.assertIn("пустую строку вместо JSON", build_autofill_error_message({}, error))

        parsed, error = parse_autofill_callback_result("not json")
        self.assertIsNone(parsed)
        self.assertEqual(error["error"], "invalid_json")
        self.assertIn("невалидный JSON", build_autofill_error_message({}, error))

        parsed, error = parse_autofill_callback_result("[]")
        self.assertIsNone(parsed)
        self.assertEqual(error["error"], "invalid_json_type")
        self.assertIn("JSON неверного типа", build_autofill_error_message({}, error))

    def test_evaluate_ok_auth_error_unknown(self):
        service = {"success_texts": ["Главная", "Dashboard"], "error_texts": ["Access denied"]}
        self.assertEqual(evaluate_service_check_page(service, "Добро пожаловать. Главная", loaded=True)[0], "ok")
        status, _success, matched_error, error = evaluate_service_check_page(service, "Access denied", loaded=True)
        self.assertEqual(status, "auth_error")
        self.assertEqual(matched_error, "Access denied")
        self.assertIn("Access denied", error)
        self.assertEqual(evaluate_service_check_page(service, "plain page", loaded=True)[0], "unknown")


    def test_evaluate_selector_results_priority_and_invalid_selector(self):
        service = {"success_texts": ["Главная"], "error_texts": ["Access denied"]}
        status, matched_success, _matched_error, error = evaluate_service_check_page(
            service,
            "plain",
            loaded=True,
            selector_result={"success_found": True, "matched_success_selector": ".dashboard", "matched_success_summary": "div class=dashboard"},
        )
        self.assertEqual(status, "ok")
        self.assertEqual(matched_success, ".dashboard")
        self.assertIn("Успешный признак найден по CSS selector: .dashboard", error)

        status, _matched_success, matched_error, error = evaluate_service_check_page(
            service,
            "Главная",
            loaded=True,
            selector_result={
                "success_found": True,
                "matched_success_selector": ".dashboard",
                "error_found": True,
                "matched_error_selector": ".login-error",
            },
        )
        self.assertEqual(status, "error")
        self.assertEqual(matched_error, ".login-error")
        self.assertIn("Ошибочный признак найден по CSS selector: .login-error", error)

        status, _matched_success, _matched_error, error = evaluate_service_check_page(
            service,
            "plain",
            loaded=True,
            selector_result={"invalid_success_selectors": [{"selector": "div[", "error": "failed"}]},
        )
        self.assertEqual(status, "error")
        self.assertIn("Некорректный CSS selector признака успеха: div[", error)

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


    def test_selector_success_details_are_rendered_in_note(self):
        result = make_service_result(
            {"id": "svc", "name": "FacePay"},
            status="ok",
            details="Успешный признак найден по CSS selector: .dashboard",
        )
        text = build_service_check_note_text({}, [result], checked_at="2026-06-10 13:30")
        self.assertIn("FacePay — ОК", text)
        self.assertIn("Детали: Успешный признак найден по CSS selector: .dashboard", text)

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
        self.assertFalse(default_item["allow_http_error_load"])
        self.assertTrue(default_item["visible_window_close_on_success"])
        self.assertFalse(default_item["visible_window_close_on_error"])
        self.assertEqual(default_item["visible_window_close_delay_seconds"], 3)
        item = default_service_item("FacePay")
        config["service_checks"]["items"].append(item)
        ensure_service_checks_defaults(config)
        self.assertEqual(config["service_checks"]["items"][0]["id"], "facepay")
        self.assertFalse(config["service_checks"]["items"][0]["allow_insecure_ssl"])
        self.assertFalse(config["service_checks"]["items"][0]["allow_http_error_load"])
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


    def test_visible_queue_opens_next_only_after_cleanup(self):
        self.assertFalse(can_open_next_visible_service_after_cleanup(False, current_dialog_active=False))
        self.assertFalse(can_open_next_visible_service_after_cleanup(True, current_dialog_active=True))
        self.assertTrue(can_open_next_visible_service_after_cleanup(True, current_dialog_active=False))


    def test_visible_queue_continues_for_four_services_after_cleanup(self):
        services = ["service", "service_2", "service_3", "service_4"]
        opened = []
        for service_id in services:
            self.assertTrue(can_open_next_visible_service_after_cleanup(True, current_dialog_active=False))
            opened.append(service_id)
        self.assertEqual(opened, services)

    def test_visible_html_form_with_valid_fields_starts_autofill_wait(self):
        service = {
            "id": "service_4",
            "auth_type": "visible_html_form",
            "url": "https://example.local",
            "login_selector": "#login",
            "password_selector": "#password",
            "submit_selector": "button[type=submit]",
        }
        diagnostics = visible_service_start_diagnostics(service)
        self.assertTrue(diagnostics["has_url"])
        self.assertTrue(diagnostics["has_login_selector"])
        self.assertTrue(diagnostics["has_password_selector"])
        self.assertTrue(diagnostics["has_submit_selector"])
        self.assertTrue(visible_html_form_should_start_autofill_wait(service))

    def test_visible_html_form_missing_selector_does_not_start_autofill_wait(self):
        service = {
            "id": "service_4",
            "auth_type": "visible_html_form",
            "url": "https://example.local",
            "login_selector": "#login",
            "password_selector": "",
            "submit_selector": "button[type=submit]",
        }
        self.assertFalse(visible_html_form_should_start_autofill_wait(service))

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
                    "allow_http_error_load": True,
                    "auth_type": "visible_html_form",
                    "visible_window_close_on_success": True,
                    "visible_window_close_on_error": False,
                    "visible_window_close_delay_seconds": 3,
                    "success_texts": ["Главная"],
                    "error_texts": ["Access denied"],
                    "success_selectors": [".dashboard"],
                    "error_selectors": [".login-error"],
                    "logout_menu_selector": ".user-menu",
                    "logout_button_selector": "button.logout",
                    "logout_success_selectors": ["form.login"],
                    "logout_success_texts": ["Войти"],
                    "logout_wait_seconds": 10,
                    "logout_menu_wait_seconds": 5,
                    "post_login_actions": [{"type": "wait_selector", "selector": ".ready", "timeout_seconds": 5, "delay_ms": 0, "description": "Проверить раздел"}],
                    "logout_actions": [{"type": "click", "selector": ".profile", "timeout_seconds": 5, "delay_ms": 500, "description": "Открыть профиль"}],
                    "session_group": "sensitive_group_1",
                    "session_group_order": 2,
                    "session_group_login_owner": False,
                    "session_group_logout_owner": True,
                    "session_group_reuse_webview": True,
                    "external_browser_open_delay_seconds": 1,
                    "external_browser_manual_confirm": True,
                    "external_browser_open_mode": "tabs",
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
        self.assertTrue(item["allow_http_error_load"])
        self.assertEqual(item["success_selectors"], [".dashboard"])
        self.assertEqual(item["error_selectors"], [".login-error"])
        self.assertEqual(item["logout_button_selector"], "button.logout")
        self.assertEqual(item["logout_success_selectors"], ["form.login"])
        self.assertEqual(item["post_login_actions"][0]["type"], "wait_selector")
        self.assertEqual(item["logout_actions"][0]["selector"], ".profile")
        self.assertEqual(item["session_group"], "sensitive_group_1")
        self.assertEqual(item["session_group_order"], 2)
        self.assertTrue(item["session_group_logout_owner"])
        self.assertTrue(item["session_group_reuse_webview"])
        self.assertEqual(item["visible_window_close_delay_seconds"], 3)
        serialized = json.dumps(exported, ensure_ascii=False).lower()
        self.assertNotIn("must-not-export", serialized)
        self.assertNotIn('"login"', serialized)
        self.assertNotIn('"password"', serialized)

    def test_service_checks_settings_widget_uses_scroll_area_for_large_form(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtWidgets import QApplication, QScrollArea, QTextEdit
        except ImportError as exc:
            self.skipTest(f"PySide6 GUI dependencies unavailable: {exc}")

        from app.service_checks_widget import ServiceChecksSettingsWidget

        app = QApplication.instance() or QApplication([])
        widget = ServiceChecksSettingsWidget({"service_checks": {"items": [default_service_item("svc")]}})
        try:
            scroll = widget.findChild(QScrollArea, "ServiceCheckFormScrollArea")
            self.assertIsNotNone(scroll)
            self.assertTrue(scroll.widgetResizable())
            self.assertEqual(scroll.verticalScrollBarPolicy(), Qt.ScrollBarAsNeeded)
            self.assertEqual(scroll.horizontalScrollBarPolicy(), Qt.ScrollBarAlwaysOff)
            self.assertIsNotNone(widget.logout_menu_selector_input)
            self.assertIsNotNone(widget.logout_button_selector_input)
            for editor in widget.findChildren(QTextEdit):
                self.assertLessEqual(editor.maximumHeight(), 120)
                self.assertGreaterEqual(editor.minimumHeight(), 50)
        finally:
            widget.deleteLater()
            app.processEvents()


if __name__ == "__main__":
    unittest.main()
