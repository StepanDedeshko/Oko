"""Silent session warmup for WebView-only Zabbix/OTRS integrations."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import html as html_lib
import json
import re
import webbrowser
from typing import Iterable
from urllib.parse import urljoin, urlparse

from app.credentials import load_otrs_credentials
from app.logger import get_logger
from app.permissions import ensure_duty_links, get_duty_link
from app.webengine_lifecycle import register_web_view, safe_delete_web_view

SYSTEM_ZABBIX = "zabbix"
SYSTEM_OTRS = "otrs"
MODE_SILENT = "silent"
MODE_MANUAL = "manual"


class WarmupStatus(str, Enum):
    OK = "ok"
    AUTH_REQUIRED = "auth_required"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    SKIPPED_NO_URL = "skipped_no_url"


@dataclass(frozen=True)
class WarmupTarget:
    system: str
    url: str
    label: str = ""
    profile_id: str = ""


@dataclass
class WarmupResult:
    system: str
    status: WarmupStatus
    url: str = ""
    reason: str = ""
    checked_at: datetime | None = None


def default_warmup_settings() -> dict:
    return {
        "warmup_on_startup": True,
        "silent_autologin": True,
        "check_before_tasks": True,
        "auto_show_auth_windows": False,
        "timeout_seconds": 25,
        "fresh_ok_seconds": 300,
        "last_results": {},
    }


def ensure_session_warmup_defaults(config: dict | None) -> dict:
    config = config if isinstance(config, dict) else {}
    settings = config.setdefault("session_warmup", {})
    for key, value in default_warmup_settings().items():
        settings.setdefault(key, value.copy() if isinstance(value, dict) else value)
    settings["timeout_seconds"] = max(5, min(120, int(settings.get("timeout_seconds") or 25)))
    settings["fresh_ok_seconds"] = max(30, int(settings.get("fresh_ok_seconds") or 300))
    settings.setdefault("last_results", {})
    return settings


def _valid_url(url: str) -> bool:
    url = str(url or "").strip()
    return bool(url and url.lower() != "about:blank")


def _host_key(url: str) -> str:
    parsed = urlparse(str(url or ""))
    return parsed.netloc.casefold() or str(url or "").split("/", 1)[0].casefold()


def _first_valid(candidates: Iterable[tuple[str, str, str]]) -> WarmupTarget | None:
    seen_hosts = set()
    for system, url, label in candidates:
        url = str(url or "").strip()
        if not _valid_url(url):
            continue
        host = _host_key(url)
        if host in seen_hosts:
            continue
        seen_hosts.add(host)
        return WarmupTarget(system=system, url=url, label=label)
    return None


def _product_zabbix_candidates(config: dict) -> list[tuple[str, str, str]]:
    candidates: list[tuple[str, str, str]] = []
    for product in config.get("products", []) or []:
        for page in product.get("pages", []) or product.get("dashboards", []) or []:
            page_type = str(page.get("type", "")).lower()
            url = page.get("problems_url") or page.get("url") or ""
            if _valid_url(url) and ("problem" in page_type or "zabbix" in str(url).lower()):
                candidates.append((SYSTEM_ZABBIX, url, page.get("name", "Zabbix page")))
            for graph in page.get("graphs", []) or []:
                for key in ("open_url", "zabbix_url", "external_url", "url"):
                    url = graph.get(key, "")
                    if _valid_url(url):
                        candidates.append((SYSTEM_ZABBIX, url, graph.get("title", "Zabbix graph")))
                        break
    return candidates


def collect_warmup_urls(config: dict | None) -> list[WarmupTarget]:
    """Return at most one control URL per system for silent warmup."""
    config = config if isinstance(config, dict) else {}
    ensure_duty_links(config)
    duty = config.get("duty_mode", {}) if isinstance(config.get("duty_mode"), dict) else {}
    service_checks = config.get("service_checks", {}) if isinstance(config.get("service_checks"), dict) else {}

    zabbix_candidates = [
        (SYSTEM_ZABBIX, get_duty_link(config, "live_zabbix_url"), "Live Zabbix Monitor"),
        (SYSTEM_ZABBIX, (config.get("live_zabbix_monitor") or {}).get("problems_url", ""), "Configured Zabbix Problems"),
        * _product_zabbix_candidates(config),
    ]
    otrs_candidates = [
        (SYSTEM_OTRS, get_duty_link(config, "mm_otrs_create_url"), "OTRS MM create"),
        (SYSTEM_OTRS, get_duty_link(config, "otrs_create_url"), "OTRS create"),
        (SYSTEM_OTRS, duty.get("duty_service_checks_task_url", ""), "Duty service OTRS task"),
        (SYSTEM_OTRS, duty.get("otrs_task_url", ""), "Duty OTRS task"),
        (SYSTEM_OTRS, service_checks.get("otrs_task_url", ""), "Service checks OTRS task"),
    ]
    targets = []
    for target in (_first_valid(zabbix_candidates), _first_valid(otrs_candidates)):
        if target is not None:
            targets.append(target)
    return targets


def _norm(value: str) -> str:
    value = html_lib.unescape(str(value or ""))
    return re.sub(r"\s+", " ", value).casefold()


def detect_zabbix_auth(url: str, html: str) -> tuple[WarmupStatus, str]:
    text = _norm(f"{url}\n{html}")
    not_logged_markers = [
        "вы не выполнили вход",
        "для просмотра этой страницы вы должны войти в систему",
        "возможно сессия просрочена",
        "msg-bad msg-global",
        "data-login-url",
    ]
    if any(marker in text for marker in not_logged_markers) and ("вход в систему" in text or "data-login-url" in text):
        return WarmupStatus.AUTH_REQUIRED, "zabbix_not_logged_in_message"
    login_markers = [
        "zabbix.php?action=user.login",
        "name=\"name\"",
        "name='name'",
        "name=\"password\"",
        "name='password'",
        "type=\"password\"",
        "type='password'",
        "sign in",
        "войти",
    ]
    has_password = "password" in text or "пароль" in text
    has_login_form = "login" in text and ("<form" in text or has_password)
    if any(marker in text for marker in login_markers) or has_login_form:
        return WarmupStatus.AUTH_REQUIRED, "login_form_detected"
    ok_markers = ["action=problem.view", "monitoring", "problems", "graphs", "dashboard", "zabbix"]
    if any(marker in text for marker in ok_markers) or (url and "login" not in _norm(url)):
        return WarmupStatus.OK, "page_loaded_without_login_form"
    return WarmupStatus.OK, "no_login_form_detected"


def detect_otrs_auth(url: str, html: str) -> tuple[WarmupStatus, str]:
    text = _norm(f"{url}\n{html}")
    has_action_login = "action=login" in text
    has_user_password = ("user" in text or "пользователь" in text) and ("password" in text or "пароль" in text)
    has_password_input = "type=\"password\"" in text or "type='password'" in text
    has_login_form = "<form" in text and ("login" in text or "войти" in text) and (has_user_password or has_password_input)
    if has_action_login or has_login_form:
        return WarmupStatus.AUTH_REQUIRED, "login_form_detected"
    ok_markers = ["agentticketnote", "agentticketzoom", "agentdashboard", "ticket", "dashboard", "agent"]
    if any(marker in text for marker in ok_markers) or (url and "action=login" not in _norm(url)):
        return WarmupStatus.OK, "page_loaded_without_login_form"
    return WarmupStatus.OK, "no_login_form_detected"


def detect_auth_status(system: str, url: str, html: str) -> tuple[WarmupStatus, str]:
    if system == SYSTEM_OTRS:
        return detect_otrs_auth(url, html)
    return detect_zabbix_auth(url, html)


def zabbix_login_url_from_html(current_url: str, html: str) -> str:
    match = re.search(r"data-login-url\s*=\s*['\"]([^'\"]+)['\"]", str(html or ""), re.IGNORECASE)
    if not match:
        return ""
    return urljoin(str(current_url or ""), html_lib.unescape(match.group(1)))


def build_autologin_script(credentials: dict) -> str:
    login = str((credentials or {}).get("login", "") or "")
    password = str((credentials or {}).get("password", "") or "")
    if not (login and password):
        return ""
    return f"""
    (() => {{
      const login = {json.dumps(login)};
      const password = {json.dumps(password)};
      const user = document.querySelector('input[name="name"], input[name="User"], input[name="user"], input[type="text"], input[type="email"]');
      const pass = document.querySelector('input[name="password"], input[name="Password"], input[type="password"]');
      if (!user || !pass) return false;
      user.focus(); user.value = login; user.dispatchEvent(new Event('input', {{bubbles:true}}));
      pass.focus(); pass.value = password; pass.dispatchEvent(new Event('input', {{bubbles:true}}));
      const button = document.querySelector('button[type="submit"], input[type="submit"], button, input[type="button"]');
      if (button) button.click(); else if (pass.form) pass.form.submit();
      return true;
    }})();
    """


class SessionAuthDialog:
    def __init__(self, target: WarmupTarget, profile=None, timeout_seconds=25, credentials=None, parent=None):
        from PySide6.QtCore import QTimer, QUrl
        from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout
        from PySide6.QtWebEngineCore import QWebEnginePage
        from PySide6.QtWebEngineWidgets import QWebEngineView
        self._QMessageBox = QMessageBox
        self.dialog = QDialog(parent)
        self.target = target
        self.credentials = credentials or {}
        self.dialog.setWindowTitle("Требуется авторизация Zabbix" if target.system == SYSTEM_ZABBIX else "Требуется авторизация OTRS")
        self.dialog.resize(1100, 760)
        root = QVBoxLayout(self.dialog)
        self.status_label = QLabel("Сессия истекла. Войдите в систему, затем нажмите «Продолжить».")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        self.url_label = QLabel(target.url)
        self.url_label.setWordWrap(True)
        root.addWidget(self.url_label)
        self.view = register_web_view(QWebEngineView())
        if profile is not None:
            self.view.setPage(QWebEnginePage(profile, self.view))
        root.addWidget(self.view, stretch=1)
        row = QHBoxLayout()
        self.continue_button = QPushButton("Продолжить")
        self.reload_button = QPushButton("Обновить")
        self.skip_button = QPushButton("Пропустить")
        self.browser_button = QPushButton("Открыть во внешнем браузере")
        self.close_button = QPushButton("Закрыть")
        for button in (self.continue_button, self.reload_button, self.skip_button, self.browser_button, self.close_button):
            row.addWidget(button)
        root.addLayout(row)
        self.continue_button.clicked.connect(self.verify_current_page)
        self.reload_button.clicked.connect(lambda: self.view.load(QUrl(self.target.url)))
        self.skip_button.clicked.connect(self.dialog.reject)
        self.close_button.clicked.connect(self.dialog.reject)
        self.browser_button.clicked.connect(lambda: webbrowser.open(self.target.url))
        self.view.loadStarted.connect(lambda: self.status_label.setText("Загрузка страницы входа..."))
        self.view.urlChanged.connect(lambda url: self.url_label.setText(url.toString()))
        self.view.loadFinished.connect(self._on_visible_load_finished)
        QTimer.singleShot(max(5, int(timeout_seconds)) * 1000, self._timeout_hint)
        if _valid_url(target.url):
            self.view.load(QUrl(target.url))
        else:
            self.status_label.setText("URL входа не настроен.")

    def _on_visible_load_finished(self, ok):
        self.status_label.setText("Страница загружена." if ok else "Ошибка загрузки страницы. Проверьте VPN/сеть или откройте во внешнем браузере.")

    def _timeout_hint(self):
        if self.dialog.isVisible():
            self.status_label.setText("Ожидание загрузки заняло слишком много времени. Можно обновить, открыть внешний браузер или пропустить.")

    def verify_current_page(self):
        self.view.page().toHtml(self._verify_html)

    def _verify_html(self, html: str):
        status, _reason = detect_auth_status(self.target.system, self.view.url().toString(), html)
        if status == WarmupStatus.OK:
            self.dialog.accept()
        else:
            self._QMessageBox.information(self.dialog, self.dialog.windowTitle(), "Авторизация ещё не завершена")

    def exec(self):
        try:
            return self.dialog.exec()
        finally:
            safe_delete_web_view(self.view, logger=get_logger(), context="session auth dialog")


class _SignalProxy:
    def __init__(self):
        self._callbacks = []
    def connect(self, callback):
        self._callbacks.append(callback)
    def emit(self, *args):
        for callback in list(self._callbacks):
            callback(*args)


class SessionWarmupManager:
    open_dialog_class = SessionAuthDialog

    def __init__(self, config: dict, profiles: dict | None = None, credentials: dict | None = None, parent=None):
        from PySide6.QtCore import QTimer
        self._parent = parent
        self.result_ready = _SignalProxy()
        self.status_message = _SignalProxy()
        self.finished = _SignalProxy()
        self.config = config
        self.profiles = profiles or {}
        self.credentials = credentials or {}
        self.settings = ensure_session_warmup_defaults(config)
        self.logger = get_logger()
        self.results: dict[str, WarmupResult] = {}
        self._queue: list[WarmupTarget] = []
        self._view = None
        self._current: WarmupTarget | None = None
        self._mode = MODE_SILENT
        self._silent_attempted: set[tuple[str, str]] = set()
        self._login_url_followed: set[tuple[str, str]] = set()
        self._manual_dialogs: dict[str, object] = {}
        self._timer = QTimer(parent)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)

    def is_fresh_ok(self, system: str) -> bool:
        result = self.results.get(system)
        if not result or result.status != WarmupStatus.OK or not result.checked_at:
            return False
        return datetime.now() - result.checked_at < timedelta(seconds=int(self.settings.get("fresh_ok_seconds", 300)))

    def ensure_fresh_or_start(self, systems: Iterable[str] = (SYSTEM_ZABBIX, SYSTEM_OTRS)) -> bool:
        systems = list(systems)
        if all(self.is_fresh_ok(system) for system in systems):
            return True
        self.start(systems=systems, only_stale=True, mode=MODE_SILENT)
        return False

    def start(self, systems: Iterable[str] = (SYSTEM_ZABBIX, SYSTEM_OTRS), only_stale: bool = False, mode: str = MODE_SILENT):
        systems = set(systems)
        self._mode = mode or MODE_SILENT
        self._silent_attempted.clear()
        self._login_url_followed.clear()
        self._queue = [t for t in collect_warmup_urls(self.config) if t.system in systems and (not only_stale or not self.is_fresh_ok(t.system))]
        missing = systems - {t.system for t in self._queue}
        self.logger.info("Session warmup started: mode=%s systems=%s", self._mode, ",".join(sorted(systems)))
        self.status_message.emit("Проверка сессий Zabbix/OTRS...")
        for system in missing:
            if not self.is_fresh_ok(system):
                self._record(WarmupResult(system=system, status=WarmupStatus.SKIPPED_NO_URL, reason="no_url", checked_at=datetime.now()))
        self._next()

    def open_manual_auth(self, system: str):
        targets = [t for t in collect_warmup_urls(self.config) if t.system == system]
        target = targets[0] if targets else WarmupTarget(system=system, url="", label="")
        if not _valid_url(target.url):
            self._record(WarmupResult(system, WarmupStatus.SKIPPED_NO_URL, reason="no_url", checked_at=datetime.now()))
            return False
        if system in self._manual_dialogs:
            dialog = self._manual_dialogs[system]
            if getattr(dialog, "dialog", None) is not None:
                dialog.dialog.raise_()
                dialog.dialog.activateWindow()
            return False
        dialog = self.open_dialog_class(target, profile=self._profile_for(target), timeout_seconds=self.settings.get("timeout_seconds", 25), credentials=self._credentials_for(target), parent=self._parent)
        self._manual_dialogs[system] = dialog
        try:
            accepted = dialog.exec()
        finally:
            self._manual_dialogs.pop(system, None)
        if accepted:
            self.start(systems=(system,), mode=MODE_SILENT)
        return bool(accepted)

    def _next(self):
        if not self._queue:
            self.status_message.emit("Прогрев завершён")
            self.finished.emit(self.results)
            return
        self._current = self._queue.pop(0)
        self.status_message.emit(f"{'Zabbix' if self._current.system == SYSTEM_ZABBIX else 'OTRS'}: проверка...")
        from PySide6.QtCore import QUrl
        from PySide6.QtWebEngineCore import QWebEnginePage
        from PySide6.QtWebEngineWidgets import QWebEngineView
        self._QUrl = QUrl
        self._view = register_web_view(QWebEngineView())
        profile = self._profile_for(self._current)
        if profile is not None:
            self._view.setPage(QWebEnginePage(profile, self._view))
        self._view.loadFinished.connect(self._on_load_finished)
        self._timer.start(int(self.settings.get("timeout_seconds", 25)) * 1000)
        self._view.load(self._QUrl(self._current.url))

    def _profile_for(self, target: WarmupTarget):
        if target.profile_id and target.profile_id in self.profiles:
            return self.profiles[target.profile_id]
        if target.system in self.profiles:
            return self.profiles[target.system]
        if len(self.profiles) == 1:
            return next(iter(self.profiles.values()))
        return None

    def _on_load_finished(self, ok: bool):
        if not self._current:
            return
        if not ok:
            self._timer.stop()
            self._record(WarmupResult(self._current.system, WarmupStatus.NETWORK_ERROR, self._current.url, "load_failed", datetime.now()))
            self._cleanup_view()
            self._next()
            return
        self._view.page().toHtml(self._on_html)

    def _on_html(self, html: str):
        if not self._current:
            return
        url = self._view.url().toString() if self._view else self._current.url
        status, reason = detect_auth_status(self._current.system, url, html)
        if status == WarmupStatus.AUTH_REQUIRED and self._mode == MODE_SILENT and self.settings.get("silent_autologin", True):
            if self._try_silent_auth(url, html, reason):
                return
        if status == WarmupStatus.AUTH_REQUIRED:
            self.logger.warning("Session warmup auth required: system=%s reason=%s", self._current.system, reason)
        result = WarmupResult(self._current.system, status, url, reason, datetime.now())
        self._timer.stop()
        self._record(result)
        self._cleanup_view()
        self._next()

    def _try_silent_auth(self, url: str, html: str, reason: str) -> bool:
        target = self._current
        key = (target.system, target.profile_id or _host_key(target.url))
        if key in self._silent_attempted:
            return False
        credentials = self._credentials_for(target)
        if not credentials.get("login") or not credentials.get("password"):
            return False
        if target.system == SYSTEM_ZABBIX and reason == "zabbix_not_logged_in_message" and key not in self._login_url_followed:
            login_url = zabbix_login_url_from_html(url, html)
            if login_url:
                self._login_url_followed.add(key)
                self.logger.info("Session warmup silent login attempted: system=%s result=follow_login_url", target.system)
                self._view.load(self._QUrl(login_url))
                return True
        self._silent_attempted.add(key)
        script = build_autologin_script(credentials)
        if not script:
            return False
        self.logger.info("Session warmup silent login attempted: system=%s result=started", target.system)
        self._view.page().runJavaScript(script, lambda _ok: None)
        return True

    def _credentials_for(self, target: WarmupTarget | str) -> dict:
        system = target.system if isinstance(target, WarmupTarget) else target
        if system == SYSTEM_OTRS:
            saved = self.credentials.get("otrs") or self.credentials.get("__otrs__") or {}
            return saved if (saved.get("login") or saved.get("password")) else load_otrs_credentials(self.config)
        if isinstance(target, WarmupTarget) and target.profile_id and target.profile_id in self.credentials:
            return self.credentials.get(target.profile_id) or {}
        if len([k for k in self.credentials if k not in {"otrs", "__otrs__"}]) == 1:
            key = next(k for k in self.credentials if k not in {"otrs", "__otrs__"})
            return self.credentials.get(key) or {}
        return {}

    def _on_timeout(self):
        if self._current:
            self._record(WarmupResult(self._current.system, WarmupStatus.TIMEOUT, self._current.url, "timeout", datetime.now()))
        self._cleanup_view()
        self._next()

    def _record(self, result: WarmupResult):
        self.results[result.system] = result
        self.settings.setdefault("last_results", {})[result.system] = {"status": result.status.value, "reason": result.reason, "checked_at": result.checked_at.isoformat() if result.checked_at else ""}
        if result.status == WarmupStatus.OK:
            self.logger.info("Session warmup completed: system=%s status=ok", result.system)
        elif result.status == WarmupStatus.SKIPPED_NO_URL:
            self.logger.info("Session warmup skipped: system=%s reason=no_url", result.system)
        elif result.status == WarmupStatus.TIMEOUT:
            self.logger.warning("Session warmup failed: system=%s reason=timeout", result.system)
        elif result.status == WarmupStatus.NETWORK_ERROR:
            self.logger.warning("Session warmup failed: system=%s reason=%s", result.system, result.reason)
        self.result_ready.emit(result)

    def _cleanup_view(self):
        if self._view is not None:
            try:
                self._view.loadFinished.disconnect(self._on_load_finished)
            except Exception:
                pass
            safe_delete_web_view(self._view, logger=self.logger, context="session warmup", load_handler=None)
            self._view = None
