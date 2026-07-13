"""Application main window with the critical Live Zabbix monitor enabled.

The original implementation is preserved in ``app.main_window_base``. Only
creation of the Live Zabbix page is specialized here; startup/release/theme
code remains outside this feature.
"""

from PySide6.QtCore import QTimer

import app.main_window_base as _main_window_base
from app.main_window_base import *  # noqa: F401,F403
from app.main_window_base import MainWindow as _BaseMainWindow
from app.critical_live_zabbix_widget import (
    CRITICAL_HISTORY_RETRY_DELAYS_MS,
    CriticalLiveZabbixMonitorWidget as _CriticalLiveZabbixMonitorWidget,
)
from app.critical_trigger_actions import is_critical_problem_item
from app.critical_triggers import CriticalAnalysisResult
from app.duty_mode import DutyModeWidget
from app.live_zabbix_widget import LiveZabbixMonitorWidget as _StandardLiveZabbixMonitorWidget


class CriticalLiveZabbixMonitorWidget(_CriticalLiveZabbixMonitorWidget):
    """Final integration layer that leaves the original non-critical flow intact."""

    def open_redmine_for_selected_row(self):
        selected = self._selected_live_problem_items()
        if selected and not any(is_critical_problem_item(item) for item in selected):
            # Call the original implementation directly. It invokes the inherited
            # selection helper once, so the existing same-host question is shown
            # exactly once for ordinary/special rows.
            return _StandardLiveZabbixMonitorWidget.open_redmine_for_selected_row(self)
        return super().open_redmine_for_selected_row()

    def _critical_after_ip_lookup(self, items, token: int) -> None:
        context = self._critical_context
        if not context or token != context.get("token"):
            return
        if items:
            context["item"] = items[0]
            context["items"] = [items[0]]

        definition = context["definition"]
        if not definition.slow_history_url:
            analysis = CriticalAnalysisResult(
                trigger_id=definition.id,
                analysis_text=(
                    "Критический триггер времени с последнего запроса. "
                    "Дополнительный автоматический анализ значений не требуется."
                ),
                graph_page_urls=[definition.main_graph_page_url],
                chart_image_urls=[definition.main_chart_image_url],
            )
            self._critical_analysis_complete(analysis, token)
            return

        super()._critical_after_ip_lookup(items, token)

    def _critical_history_result(self, result, stage: str, token: int) -> None:
        """Wait for metric/table population before treating a loaded page as final."""
        context = self._critical_context
        if (
            not context
            or token != context.get("token")
            or stage != context.get("stage")
        ):
            return

        payload = self._decode_history_result(result)
        attempt = int(context.get("attempt", 0))
        metric = str(payload.get("metric") or "").strip()
        rows = list(payload.get("rows") or [])
        if (
            payload.get("ok")
            and (not metric or not rows)
            and attempt < len(CRITICAL_HISTORY_RETRY_DELAYS_MS)
        ):
            delay_index = max(0, min(attempt - 1, len(CRITICAL_HISTORY_RETRY_DELAYS_MS) - 1))
            QTimer.singleShot(
                CRITICAL_HISTORY_RETRY_DELAYS_MS[delay_index],
                lambda current_stage=stage, current_token=token: self._critical_try_extract(
                    current_stage, current_token
                ),
            )
            return

        super()._critical_history_result(result, stage, token)

    def hideEvent(self, event):
        # Leaving the Live Zabbix page cancels only an unfinished hidden-history
        # read. A Redmine dialog or already-started acknowledgement may finish.
        if self._critical_history_view is not None:
            self._critical_history_token += 1
            self._finish_critical_flow()
        super().hideEvent(event)

    def cleanup(self):
        self._critical_history_token += 1
        self._finish_critical_flow()
        super().cleanup()


class MainWindow(_BaseMainWindow):
    def __init__(self, *args, **kwargs):
        # Jabbix changes app.main_window.APP_NAME before constructing the window.
        # The preserved base module must see the same runtime display name when
        # both feature branches are later combined for 0.3.7.
        _main_window_base.APP_NAME = globals().get("APP_NAME", _main_window_base.APP_NAME)
        super().__init__(*args, **kwargs)

    def create_duty_mode_page(self):
        self.duty_mode_widget = DutyModeWidget(
            config=self.config,
            profiles=self.profiles,
            credentials=self.credentials,
            graph_card_finder=self.find_graph_card_by_product_section_title,
            source_view_finder=self.find_source_view_by_product_section,
            active_product_getter=lambda: self.active_product_section()[0],
        )

        index = self.stack.addWidget(self.duty_mode_widget)
        self.dashboard_widgets.append(self.duty_mode_widget)
        self.page_has_time_buttons[index] = False

        self.live_zabbix_monitor_widget = CriticalLiveZabbixMonitorWidget(
            config=self.config,
            profiles=self.profiles,
            credentials=self.credentials,
        )
        live_index = self.stack.addWidget(self.live_zabbix_monitor_widget)
        self.dashboard_widgets.append(self.live_zabbix_monitor_widget)
        self.page_has_time_buttons[live_index] = False

        product_name = "Дежурство"
        self.product_dashboard_indexes[product_name] = [
            {
                "name": "Режим дежурства",
                "index": index,
                "has_time": False,
                "type": "duty_mode",
                "widget": self.duty_mode_widget,
            },
            {
                "name": "Live Zabbix Monitor",
                "index": live_index,
                "has_time": False,
                "type": "live_zabbix_monitor",
                "widget": self.live_zabbix_monitor_widget,
            },
        ]
