from __future__ import annotations

from PySide6.QtCore import QUrl


def install_live_zabbix_poll_url_guard() -> bool:
    """Refresh the already opened Live Zabbix page without losing its session state.

    A named Zabbix filter URL does not necessarily contain the filter conditions
    themselves. Zabbix can keep those conditions in the current user/session
    profile, so force-loading the configured URL on every timer tick may replace
    a working page with an empty filter state. The monitor therefore reloads the
    page that was successfully opened. The configured URL is used only when the
    WebView has no current page yet.
    """
    import app.live_zabbix_widget as live_widget

    cls = live_widget.LiveZabbixMonitorWidget
    if getattr(cls, "_configured_poll_url_guard_installed", False):
        return False

    def poll_now(self):
        view = getattr(self, "view", None)
        if view is None:
            return

        configured_url = str(self.problems_url() or "").strip()
        if not configured_url:
            status = getattr(self, "poll_status_label", None)
            if status is not None:
                status.setText("Ошибка: URL Live Zabbix Monitor не задан")
            return

        status = getattr(self, "poll_status_label", None)
        if status is not None:
            status.setText("Опрос страницы…")

        current_url = ""
        try:
            current_url = str(view.url().toString() or "").strip()
        except Exception:
            current_url = ""

        if current_url:
            view.reload()
        else:
            view.load(QUrl(configured_url))

    cls.poll_now = poll_now
    cls._configured_poll_url_guard_installed = True
    return True
