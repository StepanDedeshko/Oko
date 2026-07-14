from __future__ import annotations

from PySide6.QtCore import QUrl


def install_live_zabbix_poll_url_guard() -> bool:
    """Always poll the configured Live Zabbix URL, never a mutated WebView URL.

    Zabbix can remember the last active Problems filter for the current user and
    can redirect/rewrite the page loaded in the hidden WebView.  The old monitor
    used ``reload()``, so after such a change it kept polling the rewritten page
    instead of the URL saved in Oko settings.  Loading the configured URL on
    every timer tick keeps Oko attached to its dedicated named filter.
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

        # Deliberately do not call view.reload(): the current WebView URL may
        # already have been rewritten by Zabbix's per-user filter state.
        view.load(QUrl(configured_url))

    cls.poll_now = poll_now
    cls._configured_poll_url_guard_installed = True
    return True
