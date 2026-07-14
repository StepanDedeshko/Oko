from __future__ import annotations


_OLD_AUTH_BLOCK = r"""  var loginDetected = !!document.querySelector('input[type=password], input[name*=password i], form[action*=login i]') || /login|sign[ -]?in|вход/i.test(document.title || '');
  var loginButton = document.querySelector('button#login[name=login], button#login, button[name=login]');
  var zabbixAuthRequired = !!(loginButton && loginButton.getAttribute('data-login-url') && document.querySelector('output.msg-bad.msg-global') && /Вы не выполнили вход|Для просмотра этой страницы вы должны войти в систему|Возможно сессия просрочена или был изменен пароль/i.test(text(document.body)));
  if (zabbixAuthRequired) {
    var authDebug = {title: String(document.title || '').slice(0, 160), url_path: safeUrl(document.location.href), login_detected: true, auth_required: true, data_login_url: loginButton.getAttribute('data-login-url') || '', table_count: tables.length, tr_count: rows.length, header_map: {}, candidate_count: 0, problem_count: 0, zero_reason: 'auth_required', sample_rows: []};
    return JSON.stringify({ok: false, auth_required: true, data_login_url: loginButton.getAttribute('data-login-url') || '', login_detected: true, items: [], separators: [], safe_debug: authDebug, zero_reason: 'auth_required'});
  }
"""

_NEW_AUTH_BLOCK = r"""  var loginDetected = !!document.querySelector('input[type=password], input[name*=password i], form[action*=login i]') || /login|sign[ -]?in|вход/i.test(document.title || '');
  var loginButton = document.querySelector('button#login, input#login, a#login, button[name=login], input[name=login], a[name=login]');
  var authBodyText = text(document.body);
  var authMessage = document.querySelector('output.msg-bad, .msg-bad, [role=alert]');
  var authTextMatched = /Вы не выполнили вход|Для просмотра этой страницы вы должны войти в систему|Возможно сессия просрочена или был изменен пароль/i.test(authBodyText);
  function loginTargetFromButton(button) {
    if (!button) return '';
    var target = button.getAttribute('data-login-url') || button.getAttribute('href') || '';
    if (!target) {
      var onclick = button.getAttribute('onclick') || '';
      var match = onclick.match(/(?:window\.)?location(?:\.href)?\s*=\s*['\"]([^'\"]+)['\"]/i)
        || onclick.match(/(?:window\.)?location\.(?:assign|replace)\(\s*['\"]([^'\"]+)['\"]/i);
      if (match) target = match[1] || '';
    }
    if (!target && button.form) target = button.form.getAttribute('action') || '';
    return target ? abs(target) : '';
  }
  var loginTarget = loginTargetFromButton(loginButton);
  var warningTitle = /предупреждение|warning/i.test(document.title || '');
  var zabbixAuthRequired = !!(loginButton && authTextMatched && (authMessage || warningTitle));
  if (zabbixAuthRequired) {
    var authDebug = {title: String(document.title || '').slice(0, 160), url_path: safeUrl(document.location.href), login_detected: true, auth_required: true, click_login_button: true, data_login_url: loginTarget, table_count: tables.length, tr_count: rows.length, header_map: {}, candidate_count: 0, problem_count: 0, zero_reason: 'auth_required', sample_rows: []};
    return JSON.stringify({ok: false, auth_required: true, click_login_button: true, data_login_url: loginTarget, login_detected: true, items: [], separators: [], safe_debug: authDebug, zero_reason: 'auth_required'});
  }
"""


def patch_dom_parser_script(script: str) -> str:
    """Relax detection for the real two-step Zabbix warning page."""
    source = str(script or "")
    if _NEW_AUTH_BLOCK in source:
        return source
    if _OLD_AUTH_BLOCK not in source:
        raise RuntimeError("Live Zabbix auth parser anchor was not found")
    return source.replace(_OLD_AUTH_BLOCK, _NEW_AUTH_BLOCK, 1)


def install_live_zabbix_two_step_auth_fix() -> bool:
    """Detect and pass the intermediate Zabbix warning/login-button page."""
    import app.live_zabbix as live_model
    import app.live_zabbix_widget as live_widget

    cls = live_widget.LiveZabbixMonitorWidget
    if getattr(cls, "_two_step_warning_auth_installed", False):
        return False

    patched = patch_dom_parser_script(live_widget.DOM_PARSER_SCRIPT)
    live_widget.DOM_PARSER_SCRIPT = patched
    live_model.DOM_PARSER_SCRIPT_PLACEHOLDER = patch_dom_parser_script(
        live_model.DOM_PARSER_SCRIPT_PLACEHOLDER
    )

    original_silent_autologin = cls._silent_zabbix_autologin

    def _silent_zabbix_autologin(self, payload):
        payload = payload or {}
        if not payload.get("click_login_button"):
            return original_silent_autologin(self, payload)
        if self._zabbix_auth_retrying:
            return

        creds = self._zabbix_saved_credentials()
        if not creds.get("login") or not creds.get("password"):
            self.poll_status_label.setText("Zabbix: нет сохранённых доступов")
            self._update_diagnostics(
                payload or {"safe_debug": {"auth_status": "missing_credentials"}, "items": []},
                status_text="missing_credentials",
            )
            return

        page = self.view.page() if self.view is not None else None
        if page is None:
            return

        self._zabbix_auth_retrying = True
        self.poll_status_label.setText("Zabbix: открываю форму входа…")
        click_script = r"""
(function() {
  var button = document.querySelector('button#login, input#login, a#login, button[name=login], input[name=login], a[name=login]');
  if (!button) return JSON.stringify({clicked:false, reason:'login_button_not_found'});
  button.click();
  return JSON.stringify({clicked:true});
})();
"""

        def after_click(_result):
            live_widget.QTimer.singleShot(
                1200,
                lambda: self._fill_zabbix_login_form(creds, 1),
            )

        live_widget.run_javascript_if_alive(page, click_script, after_click)

    cls._silent_zabbix_autologin = _silent_zabbix_autologin
    cls._two_step_warning_auth_installed = True
    return True
