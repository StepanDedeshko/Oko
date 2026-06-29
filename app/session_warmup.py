"""Session warmup for WebView-only Zabbix/OTRS integrations.

The pure helpers in this module are intentionally testable without real
internal Zabbix/OTRS sites.  Qt/WebEngine classes are used only by the runtime
manager and authorization dialog.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import html as html_lib
import json
import re
import webbrowser
from typing import Callable, Iterable

from app.logger import get_logger
from app.permissions import ensure_duty_links, get_duty_link
from app.webengine_lifecycle import register_web_view, safe_delete_web_view

SYSTEM_ZABBIX = "zabbix"
SYSTEM_OTRS = "otrs"


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
        "check_before_tasks": True,
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


def _add_unique(targets: list[WarmupTarget], seen: set[tuple[str, str]], system: str, url: str, label: str):
    url = str(url or "").strip()
    if not url:
        return
    key = (system, url)
    if key not in seen:
        seen.add(key)
        targets.append(WarmupTarget(system=system, url=url, label=label))


def collect_warmup_urls(config: dict | None) -> list[WarmupTarget]:
    config = config if isinstance(config, dict) else {}
    ensure_duty_links(config)
    targets: list[WarmupTarget] = []
    seen: set[tuple[str, str]] = set()

    _add_unique(targets, seen, SYSTEM_ZABBIX, get_duty_link(config, "live_zabbix_url"), "Live Zabbix Monitor")
    _add_unique(targets, seen, SYSTEM_OTRS, get_duty_link(config, "mm_otrs_create_url"), "OTRS MM create")
    _add_unique(targets, seen, SYSTEM_OTRS, get_duty_link(config, "otrs_create_url"), "OTRS create")

    duty = config.get("duty_mode", {}) if isinstance(config.get("duty_mode"), dict) else {}
    for key in ("duty_zabbix_task_url", "current_ticket_url"):
        _add_unique(targets, seen, SYSTEM_OTRS if "otrs" in str(duty.get(key, "")).lower() else SYSTEM_ZABBIX, duty.get(key, ""), key)
    for key in ("duty_service_checks_task_url", "otrs_task_url"):
        _add_unique(targets, seen, SYSTEM_OTRS, duty.get(key, ""), key)

    service_checks = config.get("service_checks", {}) if isinstance(config.get("service_checks"), dict) else {}
    _add_unique(targets, seen, SYSTEM_OTRS, service_checks.get("otrs_task_url", ""), "Service checks OTRS task")

    for product in config.get("products", []) or []:
        for page in product.get("pages", []) or product.get("dashboards", []) or []:
            page_type = str(page.get("type", "")).lower()
            url = page.get("url") or page.get("problems_url")
            if url and ("problem" in page_type or "zabbix" in str(url).lower()):
                _add_unique(targets, seen, SYSTEM_ZABBIX, url, page.get("name", "Zabbix page"))
            for graph in page.get("graphs", []) or []:
                for key in ("url", "open_url", "zabbix_url", "external_url"):
                    _add_unique(targets, seen, SYSTEM_ZABBIX, graph.get(key, ""), graph.get("title", "Zabbix graph"))
    return targets


def _norm(value: str) -> str:
    value = html_lib.unescape(str(value or ""))
    return re.sub(r"\s+", " ", value).casefold()


def detect_zabbix_auth(url: str, html: str) -> tuple[WarmupStatus, str]:
    text = _norm(f"{url}\n{html}")
    login_markers = ["zabbix.php?action=user.login", "name=\"name\"", "name='name'", "name=\"password\"", "name='password'", "sign in", "войти"]
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
    has_login_form = "<form" in text and ("login" in text or "войти" in text) and has_user_password
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


class SessionAuthDialog:
    def __init__(self, target: WarmupTarget, profile=None, timeout_seconds=25, credentials=None, parent=None):
        from PySide6.QtCore import QTimer, QUrl
        from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout
        from PySide6.QtWebEngineCore import QWebEnginePage
        from PySide6.QtWebEngineWidgets import QWebEngineView
        self._QDialog = QDialog
        self._QMessageBox = QMessageBox
        self.dialog = QDialog(parent)
        self.target = target
        self.credentials = credentials or {}
        self._autologin_attempted = False
        self.dialog.setWindowTitle("Требуется авторизация Zabbix" if target.system == SYSTEM_ZABBIX else "Требуется авторизация OTRS")
        self.dialog.resize(1100, 760)
        root = QVBoxLayout(self.dialog)
        label = QLabel("Сессия истекла. Войдите в систему, затем нажмите «Продолжить».")
        label.setWordWrap(True)
        root.addWidget(label)
        self.view = register_web_view(QWebEngineView())
        if profile is not None:
            self.view.setPage(QWebEnginePage(profile, self.view))
        root.addWidget(self.view, stretch=1)
        row = QHBoxLayout()
        self.continue_button = QPushButton("Продолжить")
        self.skip_button = QPushButton("Пропустить")
        self.browser_button = QPushButton("Открыть во внешнем браузере")
        self.close_button = QPushButton("Закрыть")
        for button in (self.continue_button, self.skip_button, self.browser_button, self.close_button):
            row.addWidget(button)
        root.addLayout(row)
        self.continue_button.clicked.connect(self.verify_current_page)
        self.skip_button.clicked.connect(self.dialog.reject)
        self.close_button.clicked.connect(self.dialog.reject)
        self.browser_button.clicked.connect(lambda: webbrowser.open(self.target.url))
        self.view.loadFinished.connect(self._on_visible_load_finished)
        QTimer.singleShot(max(5, int(timeout_seconds)) * 1000, self._timeout_hint)
        self.view.load(QUrl(self.target.url))

    def _on_visible_load_finished(self, ok):
        if ok and not self._autologin_attempted:
            self._autologin_attempted = True
            self._try_autologin()

    def _try_autologin(self):
        login = str(self.credentials.get("login", "") or "")
        password = str(self.credentials.get("password", "") or "")
        if not (login and password):
            return
        script = f"""
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
        self.view.page().runJavaScript(script)

    def _timeout_hint(self):
        if self.dialog.isVisible():
            self.dialog.setWindowTitle(self.dialog.windowTitle() + " — можно пропустить")

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
        self.start(systems=systems, only_stale=True)
        return False

    def start(self, systems: Iterable[str] = (SYSTEM_ZABBIX, SYSTEM_OTRS), only_stale: bool = False):
        systems = set(systems)
        self._queue = [t for t in collect_warmup_urls(self.config) if t.system in systems and (not only_stale or not self.is_fresh_ok(t.system))]
        missing = systems - {t.system for t in self._queue}
        self.logger.info("Session warmup started: systems=%s", ",".join(sorted(systems)))
        self.status_message.emit("Проверка сессий Zabbix/OTRS...")
        for system in missing:
            if not self.is_fresh_ok(system):
                self._record(WarmupResult(system=system, status=WarmupStatus.SKIPPED_NO_URL, reason="no_url", checked_at=datetime.now()))
        self._next()

    def _next(self):
        if not self._queue:
            self.status_message.emit("Прогрев завершён")
            self.finished.emit(self.results)
            return
        self._current = self._queue.pop(0)
        self.status_message.emit(f"Проверка сессии {'Zabbix' if self._current.system == SYSTEM_ZABBIX else 'OTRS'}...")
        from PySide6.QtCore import QUrl
        from PySide6.QtWebEngineCore import QWebEnginePage
        from PySide6.QtWebEngineWidgets import QWebEngineView
        self._QUrl = QUrl
        self._view = register_web_view(QWebEngineView())
        profile = self.profiles.get(self._current.system) or next(iter(self.profiles.values()), None)
        if profile is not None:
            self._view.setPage(QWebEnginePage(profile, self._view))
        self._view.loadFinished.connect(self._on_load_finished)
        self._timer.start(int(self.settings.get("timeout_seconds", 25)) * 1000)
        self._view.load(self._QUrl(self._current.url))

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
        self._timer.stop()
        url = self._view.url().toString() if self._view else self._current.url
        status, reason = detect_auth_status(self._current.system, url, html)
        if status == WarmupStatus.AUTH_REQUIRED:
            self._cleanup_view()
            self.logger.warning("Session warmup auth required: system=%s reason=%s", self._current.system, reason)
            from PySide6.QtWidgets import QDialog
            dialog = SessionAuthDialog(self._current, profile=self.profiles.get(self._current.system), timeout_seconds=self.settings.get("timeout_seconds", 25), credentials=self._credentials_for(self._current.system), parent=self._parent)
            accepted = dialog.exec() == QDialog.Accepted
            status, reason = (WarmupStatus.OK, "manual_login_completed") if accepted else (WarmupStatus.AUTH_REQUIRED, "manual_login_skipped")
        result = WarmupResult(self._current.system, status, url, reason, datetime.now())
        self._record(result)
        self._cleanup_view()
        self._next()

    def _credentials_for(self, system: str) -> dict:
        if system == SYSTEM_OTRS:
            return self.credentials.get("otrs") or self.credentials.get("__otrs__") or {}
        for key, value in self.credentials.items():
            if key not in {"otrs", "__otrs__"} and isinstance(value, dict) and (value.get("login") or value.get("password")):
                return value
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
            self.logger.info("Session warmup loaded: system=%s status=ok", result.system)
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
