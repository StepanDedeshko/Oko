"""Runtime integration for the user-facing Reports section.

The project intentionally keeps ``app.main_window_base`` stable while release
features are layered at runtime. This module follows the same pattern: it adds
one page to the existing stack and one home-menu action without replacing user
configuration or credentials.
"""
from __future__ import annotations

from app.reports_widget import ReportsWidget

_INSTALLED = False


def install_reports_integration() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    import app.home_config as home_config
    import app.main_window_base as main_window_base

    base_window = main_window_base.MainWindow
    original_init = base_window.__init__
    original_stop = base_window.stop_background_activity_for_exit

    def window_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        if getattr(self, "reports_widget", None) is not None:
            return
        self.reports_widget = ReportsWidget(
            config=self.config,
            profiles=self.profiles,
            credentials=self.credentials,
            parent=self,
        )
        self.reports_page_index = self.stack.addWidget(self.reports_widget)
        self.dashboard_widgets.append(self.reports_widget)
        self.page_has_time_buttons[self.reports_page_index] = False

    def open_reports_page(self):
        index = getattr(self, "reports_page_index", None)
        if index is None:
            return
        self.stack.setCurrentIndex(index)
        self.set_time_selector_visible(False)
        self.update_duty_section_switch(None)
        self.pause_inactive_web_dashboards()
        self.log_memory_status()

    def stop_background_activity_for_exit(self):
        reports = getattr(self, "reports_widget", None)
        if reports is not None and hasattr(reports, "cleanup"):
            try:
                reports.cleanup()
            except Exception:
                logger = getattr(self, "logger", None)
                if logger is not None:
                    logger.exception("Failed to cleanup ReportsWidget")
        return original_stop(self)

    base_window.__init__ = window_init
    base_window.open_reports_page = open_reports_page
    base_window.stop_background_activity_for_exit = stop_background_activity_for_exit

    home_page = home_config.HomePageWidget
    original_visible_actions = home_page.visible_main_actions
    original_open_action = home_page.open_main_action

    def visible_main_actions(self):
        actions = list(original_visible_actions(self) or [])
        if "Отчеты" not in actions:
            try:
                duty_index = actions.index("Перейти в режим дежурства")
            except ValueError:
                duty_index = -1
            actions.insert(duty_index + 1, "Отчеты")
        return actions

    def open_main_action(self, action_name):
        if action_name == "Отчеты":
            window = self.window()
            opener = getattr(window, "open_reports_page", None)
            if opener is not None:
                opener()
            return
        return original_open_action(self, action_name)

    home_page.visible_main_actions = visible_main_actions
    home_page.open_main_action = open_main_action
