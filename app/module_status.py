from dataclasses import dataclass, replace
from typing import Iterable

from app.config import ensure_duty_triggers_defaults
from app.webengine_lifecycle import register_web_view, safe_delete_web_view

ROW_CHECKING = "checking"
ROW_ONLINE = "online"
ROW_LOGIN_REQUIRED = "login required"
ROW_ERROR = "error"
ROW_TIMEOUT = "timeout"
ROW_DISABLED = "disabled"
ROW_NOT_CONFIGURED = "not configured"

AGG_ONLINE = "online"
AGG_PARTIAL = "partial"
AGG_DISABLED = "disabled"
AGG_OFFLINE = "offline"

AGG_LABELS = {
    AGG_ONLINE: "Модули: online",
    AGG_PARTIAL: "Модули: частично",
    AGG_DISABLED: "Модули: отключены",
    AGG_OFFLINE: "Модули: offline",
}
AGG_COLORS = {
    AGG_ONLINE: "green",
    AGG_PARTIAL: "yellow",
    AGG_DISABLED: "gray",
    AGG_OFFLINE: "red",
}


@dataclass(frozen=True)
class ModuleStatusTarget:
    product_name: str
    section_name: str
    url: str
    zabbix_id: str = ""
    mode_name: str = ""
    status: str = ROW_CHECKING
    reason: str = "Ожидает проверки"
    source: str = "dashboard"
    target_product: str = ""
    target_section: str = ""
    target_graph_title: str = ""


def _normalize_lookup_text(value):
    return " ".join(str(value or "").split()).casefold()


def find_dashboard_by_product_section(config, product_name, section_name):
    target_product = _normalize_lookup_text(product_name)
    target_section = _normalize_lookup_text(section_name)
    if not target_product or not target_section:
        return None
    for product in config.get("products", []) or []:
        if _normalize_lookup_text(product.get("name")) != target_product:
            continue
        for dashboard in product.get("dashboards", []) or []:
            if _normalize_lookup_text(dashboard.get("name")) == target_section:
                return dashboard
    return None

def _text(value):
    return str(value or "").strip()


def _is_enabled(item):
    return bool(item.get("enabled", True))


def _append_target(targets, product, dashboard, url, mode_name="", source="dashboard", **extra):
    url = _text(url)
    if not url:
        return
    targets.append(ModuleStatusTarget(
        product_name=_text(product.get("name")) or "Продукт",
        section_name=_text(dashboard.get("name")) or "Раздел",
        mode_name=_text(mode_name),
        url=url,
        zabbix_id=_text(dashboard.get("zabbix_id")),
        source=source,
        **extra,
    ))


def _mode_url_for_trigger(dashboard, trigger_mode):
    modes = dashboard.get("modes", []) or []
    index = {"mode_1": 0, "mode_2": 1}.get(_text(trigger_mode))
    if index is not None and index < len(modes):
        url = _text(modes[index].get("url"))
        if url:
            return url
    return _text(dashboard.get("url"))


def collect_module_status_targets(config):
    targets = []
    products_by_name = {}
    for product in config.get("products", []) or []:
        if not _is_enabled(product):
            continue
        product_name = _text(product.get("name")) or "Продукт"
        products_by_name[product_name.casefold()] = product
        for dashboard in product.get("dashboards", []) or []:
            if not _is_enabled(dashboard):
                continue
            page_type = _text(dashboard.get("type"))
            if page_type in {"problems_page", "dashboard_page"}:
                _append_target(targets, product, dashboard, dashboard.get("url"))
            elif page_type == "mode_pages":
                _append_target(targets, product, dashboard, dashboard.get("url"))
                for mode in dashboard.get("modes", []) or []:
                    _append_target(targets, product, dashboard, mode.get("url"), mode_name=mode.get("name"))
            elif page_type == "graphs_grid":
                for graph in dashboard.get("graphs", []) or []:
                    title = _text(graph.get("title")) or "График"
                    _append_target(targets, product, dashboard, graph.get("url"), mode_name=title)
                    if _text(graph.get("open_url")):
                        _append_target(targets, product, dashboard, graph.get("open_url"), mode_name=f"{title} / открытие")

    trigger_settings = ensure_duty_triggers_defaults(config)
    if trigger_settings.get("enabled", True):
        for trigger in trigger_settings.get("items", []) or []:
            if not _is_enabled(trigger):
                continue
            dashboard = find_dashboard_by_product_section(config, trigger.get("source_product"), trigger.get("source_section"))
            if not dashboard:
                continue
            source_product = products_by_name.get(_text(trigger.get("source_product")).casefold()) or {"name": trigger.get("source_product")}
            mode = _text(trigger.get("mode"))
            url = _mode_url_for_trigger(dashboard, mode) if dashboard.get("type") == "mode_pages" else _text(dashboard.get("url"))
            label = " / ".join(part for part in [
                _text(trigger.get("source_product")),
                _text(trigger.get("source_section")),
                mode,
                _text(trigger.get("display_name")),
            ] if part)
            _append_target(
                targets, source_product, dashboard, url,
                mode_name=label or mode,
                source="duty_trigger",
                target_product=_text(trigger.get("target_product")),
                target_section=_text(trigger.get("target_section")),
                target_graph_title=_text(trigger.get("target_graph_title")),
            )
    return targets


def aggregate_module_status(targets: Iterable[ModuleStatusTarget]):
    targets = [t for t in targets if _text(t.url)]
    if not targets:
        state = AGG_DISABLED
    else:
        online = sum(1 for t in targets if t.status == ROW_ONLINE)
        if online == len(targets):
            state = AGG_ONLINE
        elif online > 0:
            state = AGG_PARTIAL
        else:
            state = AGG_OFFLINE
    return {"state": state, "label": AGG_LABELS[state], "color": AGG_COLORS[state]}


def detect_login_required(url, html):
    haystack = f"{url}\n{html}".casefold()
    return (
        "вы не выполнили вход" in haystack
        or 'id="login"' in haystack
        or "button#login" in haystack
        or ("zabbix" in haystack and ("name=\"password\"" in haystack or "name='password'" in haystack) and "login" in haystack)
        or "zabbix.php?action=dashboard.view" in haystack and "login" in haystack
    )


class _CallbackSignal:
    def __init__(self):
        self._callbacks = []

    def connect(self, callback):
        self._callbacks.append(callback)

    def emit(self, *args):
        for callback in list(self._callbacks):
            callback(*args)


class ModuleStatusChecker:
    def __init__(self, targets, profiles=None, timeout_ms=15000, parent=None):
        from PySide6.QtCore import QTimer

        self._QTimer = QTimer
        self.parent = parent
        self.targets_changed = _CallbackSignal()
        self.finished = _CallbackSignal()
        self.targets = list(targets)
        self.profiles = profiles or {}
        self.timeout_ms = timeout_ms
        self.index = -1
        self.view = None
        self.page = None
        self.timer = QTimer(parent)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._timeout_current)

    def start(self):
        if not self.targets:
            self.finished.emit([])
            return
        self._next()

    def _next(self):
        self.index += 1
        if self.index >= len(self.targets):
            self._cleanup_view()
            self.finished.emit(self.targets)
            return
        target = self.targets[self.index]
        self.targets[self.index] = replace(target, status=ROW_CHECKING, reason="Проверяю страницу")
        self.targets_changed.emit(self.targets)
        self._cleanup_view()
        from PySide6.QtCore import QUrl
        from PySide6.QtWebEngineCore import QWebEnginePage
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self.view = register_web_view(QWebEngineView())
        self.view.resize(1, 1)
        profile = self.profiles.get(target.zabbix_id)
        if profile is not None:
            self.page = QWebEnginePage(profile, self.view)
            self.view.setPage(self.page)
        self.timer.start(self.timeout_ms)
        self.view.loadFinished.connect(self._loaded)
        self.view.load(QUrl(target.url))

    def _loaded(self, ok):
        self.timer.stop()
        if not ok:
            self._finish_current(ROW_ERROR, "Страница не загрузилась")
            return
        self.view.page().toHtml(lambda html: self._html_ready(html))

    def _html_ready(self, html):
        target = self.targets[self.index]
        if detect_login_required(target.url, html):
            self._finish_current(ROW_LOGIN_REQUIRED, "Требуется авторизация Zabbix")
        else:
            self._finish_current(ROW_ONLINE, "Страница доступна")

    def _timeout_current(self):
        self._finish_current(ROW_TIMEOUT, "Timeout загрузки")

    def _finish_current(self, status, reason):
        self.targets[self.index] = replace(self.targets[self.index], status=status, reason=reason)
        self.targets_changed.emit(self.targets)
        self._QTimer.singleShot(150, self._next)

    def _cleanup_view(self):
        if self.view is not None:
            safe_delete_web_view(self.view, logger=None, context="module status checker")
        self.view = None
        self.page = None
