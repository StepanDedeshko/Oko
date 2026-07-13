"""Critical-trigger integration for the existing Live Zabbix widget.

The base monitor remains unchanged for standard and special triggers.  This
subclass adds the guarded critical-only Redmine path and reuses the same
persistent Zabbix/Redmine WebEngine profiles.
"""

from __future__ import annotations

from datetime import datetime
import json

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMenu, QMessageBox

from app.critical_trigger_actions import (
    COPY_TASK_COMMENT_ACTION,
    MM_OTRS_ACTION,
    NO_ACTION_REQUIRED_ACTION,
    OBSERVED_ACTION,
    REDMINE_ACTION,
    can_use_processing_action,
    critical_selection_error,
    is_critical_problem_item,
    redmine_auto_ack_enabled_for_items,
    should_offer_same_host_expansion,
)
from app.critical_triggers import (
    CriticalAnalysisResult,
    HISTORY_EXTRACTION_SCRIPT,
    analyze_critical_history,
    analyze_slow_share_only,
    build_redmine_description,
    build_zabbix_comment,
    match_critical_trigger,
    validate_history_payload,
)
from app.live_zabbix import ensure_live_monitor_defaults
from app.live_zabbix_widget import (
    REDMINE_DESCRIPTION_PLACEHOLDER,
    REDMINE_URL_LENGTH_LIMIT,
    REDMINE_WATCHER_USER_IDS,
    LiveZabbixMonitorWidget,
    RedmineCreateDialog,
)
from app.templates import get_redmine_task_template
from app.webengine_lifecycle import (
    register_web_view,
    run_javascript_if_alive,
    safe_delete_web_view,
)


CRITICAL_HISTORY_TIMEOUT_MS = 12_000
CRITICAL_HISTORY_RETRY_DELAYS_MS = (250, 800, 1_600, 2_800)
CRITICAL_ANALYSIS_FAILED_TEXT = (
    "Не удалось автоматически получить или разобрать значения Zabbix.\n"
    "Требуется ручная проверка графика."
)


class CriticalLiveZabbixMonitorWidget(LiveZabbixMonitorWidget):
    """Live Zabbix monitor with an isolated critical-trigger Redmine flow."""

    def __init__(self, config, profiles, credentials=None, parent=None):
        self._critical_history_view = None
        self._critical_history_token = 0
        self._critical_action_active = False
        self._critical_context = None
        self._critical_issue_callbacks_seen = set()
        super().__init__(config, profiles, credentials=credentials, parent=parent)

    # ------------------------------------------------------------------
    # Selection and processing-action guards
    # ------------------------------------------------------------------
    def _show_guard_message(self, title: str, message: str) -> None:
        self.poll_status_label.setText(message)
        QMessageBox.warning(self, title, message)

    def _guard_processing_action(self, action: str, title: str):
        items = self._selected_live_problem_items()
        allowed, message = can_use_processing_action(action, items)
        if not allowed:
            self._show_guard_message(title, message)
            return None
        return items

    def _choose_redmine_items_for_selection(self, title="Redmine"):
        items = self._selected_live_problem_items()
        if not items:
            return []

        error = critical_selection_error(items)
        if error:
            self._show_guard_message(title, error)
            return []

        if any(is_critical_problem_item(item) for item in items):
            # Critical rows are always handled one-by-one and never expanded to
            # all visible problems of the same host.
            return items

        if should_offer_same_host_expansion(items):
            return super()._choose_redmine_items_for_selection(title)
        return items

    def open_mm_otrs_for_selected_row(self):
        if self._guard_processing_action(MM_OTRS_ACTION, "ОТРС ММ") is None:
            return
        super().open_mm_otrs_for_selected_row()

    def mark_selected_as_observed(self):
        if self._guard_processing_action(OBSERVED_ACTION, "Наблюдаю") is None:
            return
        super().mark_selected_as_observed()

    def mark_selected_as_no_action_required(self):
        if self._guard_processing_action(NO_ACTION_REQUIRED_ACTION, "Не требует обработки") is None:
            return
        super().mark_selected_as_no_action_required()

    def copy_task_comment_to_selected(self):
        if self._guard_processing_action(COPY_TASK_COMMENT_ACTION, "Zabbix") is None:
            return
        super().copy_task_comment_to_selected()

    def _show_table_context_menu(self, position):
        cell = self.table.itemAt(position)
        if cell is None:
            return

        # Right-clicking a row outside the current selection should operate on
        # that row only.  Existing multi-selection is kept when the clicked row
        # is already selected.
        if not cell.isSelected():
            self.table.clearSelection()
            self.table.selectRow(cell.row())
            self.table.setCurrentCell(cell.row(), cell.column())

        items = self._selected_live_problem_items()
        menu = QMenu(self)
        column = cell.column()
        payload = cell.data(Qt.UserRole)

        # Navigation is intentionally still available for critical rows.
        if column == 3:
            if payload:
                action = menu.addAction("Открыть узел сети в Zabbix")
                action.triggered.connect(
                    lambda _checked=False, url=str(payload): QDesktopServices.openUrl(QUrl(url))
                )
            else:
                action = menu.addAction("Ссылка на узел не найдена")
                action.setEnabled(False)
        elif column == 4:
            data = payload if isinstance(payload, dict) else {}
            graph_urls = list(data.get("graph_urls") or [])
            problem_url = str(data.get("problem_url") or "")
            if graph_urls:
                action = menu.addAction("Открыть график проблемы")
                action.triggered.connect(
                    lambda _checked=False, urls=list(graph_urls): self.open_graphs(urls)
                )
            if problem_url:
                action = menu.addAction("Открыть проблему в Zabbix")
                action.triggered.connect(
                    lambda _checked=False, url=problem_url: QDesktopServices.openUrl(QUrl(url))
                )
            if not graph_urls and not problem_url:
                action = menu.addAction("Ссылка на график/проблему не найдена")
                action.setEnabled(False)
        elif column == 6:
            if payload:
                action = menu.addAction("Открыть подтверждение Zabbix")
                action.triggered.connect(
                    lambda _checked=False, url=str(payload): self.open_acknowledgement(url)
                )
            else:
                action = menu.addAction("Ссылка на подтверждение не найдена")
                action.setEnabled(False)

        selection_error = critical_selection_error(items)
        if selection_error:
            self._show_guard_message("Критический триггер", selection_error)
            if menu.actions():
                menu.exec(self.table.viewport().mapToGlobal(position))
            return

        has_critical = any(is_critical_problem_item(item) for item in items)
        if menu.actions():
            menu.addSeparator()

        if has_critical:
            # The only state-changing action exposed for a critical row.
            redmine_action = menu.addAction("Создать задачу Redmine")
            redmine_action.triggered.connect(self.open_redmine_for_selected_row)
        else:
            redmine_action = menu.addAction("Создать Redmine по выбранным строкам")
            redmine_action.triggered.connect(self.open_redmine_for_selected_row)
            mm_otrs_action = menu.addAction("Создать задачу на ММ")
            mm_otrs_action.triggered.connect(self.open_mm_otrs_for_selected_row)
            observed_action = menu.addAction("Наблюдаю")
            observed_action.triggered.connect(self.mark_selected_as_observed)
            no_action_action = menu.addAction("Не требует обработки")
            no_action_action.triggered.connect(self.mark_selected_as_no_action_required)
            copy_action = menu.addAction("Скопировать комментарий задачи на выбранные")
            copy_action.triggered.connect(self.copy_task_comment_to_selected)

        menu.exec(self.table.viewport().mapToGlobal(position))

    # ------------------------------------------------------------------
    # Critical history collection
    # ------------------------------------------------------------------
    def open_redmine_for_selected_row(self):
        items = self._choose_redmine_items_for_selection()
        if not items:
            message = "Выберите строку проблемы Live Zabbix Monitor для создания задачи Redmine."
            if not self._selected_live_problem_items():
                self.poll_status_label.setText(message)
                QMessageBox.information(self, "Redmine", message)
            return

        if not any(is_critical_problem_item(item) for item in items):
            super().open_redmine_for_selected_row()
            return

        allowed, message = can_use_processing_action(REDMINE_ACTION, items)
        if not allowed:
            self._show_guard_message("Критический триггер", message)
            return

        if self._critical_action_active:
            self._show_guard_message(
                "Критический триггер",
                "Подготовка критического триггера уже выполняется. Дождитесь завершения текущего действия.",
            )
            return

        item = items[0]
        definition = match_critical_trigger(getattr(item, "trigger_name", ""))
        if definition is None:
            self._show_guard_message(
                "Критический триггер",
                "Не удалось определить сценарий критического триггера.",
            )
            return

        self._critical_history_token += 1
        token = self._critical_history_token
        self._critical_action_active = True
        self._critical_context = {
            "token": token,
            "item": item,
            "items": [item],
            "definition": definition,
            "slow_points": [],
            "slow_warnings": [],
            "analysis": None,
            "stage": "ip",
            "attempt": 0,
            "issue_detected": False,
        }
        self.logger.info(
            "Critical trigger matched: id=%s trigger=%s",
            definition.id,
            getattr(item, "trigger_name", ""),
        )
        self.poll_status_label.setText("Критический триггер: определяю IP узла...")

        try:
            self._enrich_redmine_host_ips(
                [item],
                lambda enriched, current_token=token: self._critical_after_ip_lookup(
                    enriched, current_token
                ),
            )
        except Exception:
            self.logger.exception("Critical IP lookup failed; continuing without IP")
            self._critical_after_ip_lookup([item], token)

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
                graph_page_urls=[definition.main_graph_page_url],
                chart_image_urls=[definition.main_chart_image_url],
            )
            self._critical_analysis_complete(analysis, token)
            return

        self.poll_status_label.setText(
            "Критический триггер: загружаю долю медленных запросов..."
        )
        self._critical_start_history_load(
            url=definition.slow_history_url,
            expected_metric=definition.expected_slow_metric,
            stage="slow",
            token=token,
        )

    def _critical_start_history_load(
        self, *, url: str, expected_metric: str, stage: str, token: int
    ) -> None:
        context = self._critical_context
        if not context or token != context.get("token"):
            return

        self._cleanup_critical_history_view()
        profile = (
            self.view.page().profile()
            if self.view is not None and self.view.page() is not None
            else None
        )
        if profile is None:
            self.logger.warning(
                "Critical history load failed: no shared profile id=%s stage=%s",
                context["definition"].id,
                stage,
            )
            self._critical_history_failed(stage, token, ["shared_profile_missing"])
            return

        view = register_web_view(QWebEngineView(self))
        view.setPage(QWebEnginePage(profile, view))
        view.hide()
        self._critical_history_view = view
        context["stage"] = stage
        context["expected_metric"] = expected_metric
        context["history_url"] = url
        context["attempt"] = 0

        self.logger.info(
            "Critical history load started: id=%s stage=%s metric=%s url=%s",
            context["definition"].id,
            stage,
            expected_metric,
            self._safe_url_for_report(url),
        )

        view.loadFinished.connect(
            lambda ok, current_token=token, current_stage=stage: self._critical_history_loaded(
                bool(ok), current_stage, current_token
            )
        )
        QTimer.singleShot(
            CRITICAL_HISTORY_TIMEOUT_MS,
            lambda current_token=token, current_stage=stage: self._critical_history_timeout(
                current_stage, current_token
            ),
        )
        view.load(QUrl(url))

    def _critical_history_loaded(self, ok: bool, stage: str, token: int) -> None:
        context = self._critical_context
        if (
            not context
            or token != context.get("token")
            or stage != context.get("stage")
        ):
            return
        if not ok:
            self._critical_history_failed(stage, token, ["load_finished_false"])
            return
        self._critical_try_extract(stage, token)

    def _critical_try_extract(self, stage: str, token: int) -> None:
        context = self._critical_context
        if (
            not context
            or token != context.get("token")
            or stage != context.get("stage")
        ):
            return
        view = self._critical_history_view
        page = view.page() if view is not None else None
        if page is None:
            self._critical_history_failed(stage, token, ["history_page_missing"])
            return

        context["attempt"] = int(context.get("attempt", 0)) + 1
        run_javascript_if_alive(
            page,
            HISTORY_EXTRACTION_SCRIPT,
            lambda result, current_stage=stage, current_token=token: self._critical_history_result(
                result, current_stage, current_token
            ),
        )

    @staticmethod
    def _decode_history_result(result):
        if isinstance(result, dict):
            return result
        if isinstance(result, str):
            try:
                return json.loads(result or "{}")
            except (TypeError, ValueError):
                return {}
        return {}

    def _critical_history_result(self, result, stage: str, token: int) -> None:
        context = self._critical_context
        if (
            not context
            or token != context.get("token")
            or stage != context.get("stage")
        ):
            return

        payload = self._decode_history_result(result)
        attempt = int(context.get("attempt", 0))
        if not payload.get("ok"):
            if attempt < len(CRITICAL_HISTORY_RETRY_DELAYS_MS):
                delay = CRITICAL_HISTORY_RETRY_DELAYS_MS[attempt]
                QTimer.singleShot(
                    delay,
                    lambda current_stage=stage, current_token=token: self._critical_try_extract(
                        current_stage, current_token
                    ),
                )
                return
            self._critical_history_failed(
                stage,
                token,
                [str(payload.get("reason") or "history_dom_not_ready")],
            )
            return

        expected_metric = str(context.get("expected_metric") or "")
        points, warnings = validate_history_payload(payload, expected_metric)
        actual_metric = str(payload.get("metric") or "")
        rows = list(payload.get("rows") or [])
        metric_valid = actual_metric == expected_metric
        parse_failed = bool(rows and not points)

        if not metric_valid:
            self.logger.warning(
                "Critical history metric mismatch: id=%s stage=%s expected=%s actual=%s",
                context["definition"].id,
                stage,
                expected_metric,
                actual_metric,
            )
            self._critical_history_failed(stage, token, warnings or ["metric_mismatch"])
            return

        self.logger.info(
            "Critical history metric validated: id=%s stage=%s metric=%s points=%s",
            context["definition"].id,
            stage,
            actual_metric,
            len(points),
        )
        if parse_failed:
            self._critical_history_failed(stage, token, warnings or ["history_parse_failed"])
            return

        self._cleanup_critical_history_view()
        definition = context["definition"]

        if stage == "slow":
            context["slow_points"] = points
            context["slow_warnings"] = warnings
            if not points:
                self._critical_history_failed(stage, token, warnings or ["slow_history_empty"])
                return

            latest = points[-1]
            self.logger.info(
                "Critical slow share parsed: id=%s metric=%s points=%s latest=%s timestamp=%s",
                definition.id,
                actual_metric,
                len(points),
                latest.value,
                latest.timestamp.isoformat(),
            )
            initial = analyze_slow_share_only(definition, points)
            if not initial.all_operations_checked:
                self._critical_analysis_complete(initial, token)
                return

            self.logger.info(
                "Critical all-operations check required: id=%s slow_value=%s",
                definition.id,
                latest.value,
            )
            self.poll_status_label.setText(
                "Критический триггер: проверяю запросы за последние 30 минут..."
            )
            self._critical_start_history_load(
                url=definition.all_operations_history_url,
                expected_metric=definition.expected_all_operations_metric,
                stage="all_operations",
                token=token,
            )
            return

        analysis = analyze_critical_history(
            definition,
            context.get("slow_points") or [],
            points,
            now=datetime.now(),
            warnings=(context.get("slow_warnings") or []) + warnings,
        )
        self._critical_analysis_complete(analysis, token)

    def _critical_history_timeout(self, stage: str, token: int) -> None:
        context = self._critical_context
        if (
            not context
            or token != context.get("token")
            or stage != context.get("stage")
            or self._critical_history_view is None
        ):
            return
        self.logger.warning(
            "Critical history timeout: id=%s stage=%s url=%s",
            context["definition"].id,
            stage,
            self._safe_url_for_report(context.get("history_url", "")),
        )
        self._critical_history_failed(stage, token, ["history_timeout"])

    def _critical_history_failed(self, stage: str, token: int, warnings) -> None:
        context = self._critical_context
        if not context or token != context.get("token"):
            return
        self._cleanup_critical_history_view()
        definition = context["definition"]
        slow_points = context.get("slow_points") or []
        include_all_operations = stage == "all_operations" and bool(slow_points)

        analysis = analyze_slow_share_only(definition, slow_points)
        if include_all_operations:
            analysis.all_operations_checked = True
            analysis.all_operations_state = "analysis_failed"
            if definition.all_operations_graph_page_url not in analysis.graph_page_urls:
                analysis.graph_page_urls.append(definition.all_operations_graph_page_url)
            if definition.all_operations_chart_image_url not in analysis.chart_image_urls:
                analysis.chart_image_urls.append(definition.all_operations_chart_image_url)
        else:
            analysis.all_operations_state = "analysis_failed"
        analysis.analysis_text = CRITICAL_ANALYSIS_FAILED_TEXT
        analysis.warnings.extend(str(value) for value in warnings or [] if str(value or ""))
        self._critical_analysis_complete(analysis, token)

    def _cleanup_critical_history_view(self) -> None:
        view = self._critical_history_view
        self._critical_history_view = None
        if view is not None:
            safe_delete_web_view(
                view,
                logger=self.logger,
                context="CriticalLiveZabbix history",
            )

    # ------------------------------------------------------------------
    # Critical Redmine and mandatory Zabbix acknowledgement
    # ------------------------------------------------------------------
    def _critical_analysis_complete(
        self, analysis: CriticalAnalysisResult, token: int
    ) -> None:
        context = self._critical_context
        if not context or token != context.get("token"):
            return
        context["analysis"] = analysis
        context["stage"] = "redmine"
        self.logger.info(
            "Critical analysis completed: id=%s slow_value=%s all_operations_state=%s warnings=%s",
            context["definition"].id,
            analysis.slow_value,
            analysis.all_operations_state,
            analysis.warnings,
        )
        self.poll_status_label.setText(
            "Критический триггер: формирую описание Redmine..."
        )
        self._open_critical_redmine_dialog(token)

    def _build_critical_redmine_url(self, context):
        item = context["item"]
        definition = context["definition"]
        analysis = context["analysis"]
        template = get_redmine_task_template(self.config, special=True)
        create_url = str(template.get("create_url") or "").strip()
        if not create_url:
            return "", "URL создания задачи Redmine не задан в настройках специального шаблона."

        subject = self._redmine_subject([item])
        ip = self._redmine_item_ip_text(item) or "не найден"
        description = build_redmine_description(
            definition,
            getattr(item, "trigger_name", ""),
            getattr(item, "host", ""),
            ip,
            analysis,
        )

        default_params = {
            "issue[tracker_id]": str(template.get("tracker_id") or "32"),
            "issue[assigned_to_id]": str(template.get("assigned_to_id") or "1121"),
            "issue[custom_field_values][94]": str(
                template.get("custom_field_94") or "Не применим"
            ),
            "issue[watcher_user_ids][]": REDMINE_WATCHER_USER_IDS,
        }
        if template.get("priority_id"):
            default_params["issue[priority_id]"] = str(template.get("priority_id"))

        full_url = self._merge_redmine_url_params(
            create_url,
            {
                "issue[subject]": subject,
                "issue[description]": description,
            },
            default_params,
        )
        if len(full_url) <= REDMINE_URL_LENGTH_LIMIT:
            self._pending_redmine_description = ""
            return full_url, ""

        short_url = self._merge_redmine_url_params(
            create_url,
            {
                "issue[subject]": subject,
                "issue[description]": REDMINE_DESCRIPTION_PLACEHOLDER,
            },
            default_params,
        )
        self._pending_redmine_description = description
        return short_url, ""

    def _open_critical_redmine_dialog(self, token: int) -> None:
        context = self._critical_context
        if not context or token != context.get("token"):
            return
        try:
            redmine_url, warning = self._build_critical_redmine_url(context)
            if not redmine_url:
                self._show_guard_message("Redmine", warning or "Не удалось собрать ссылку Redmine.")
                self._finish_critical_flow(token)
                return
            if warning:
                QMessageBox.warning(self, "Redmine", warning)

            self.logger.info(
                "Critical Redmine dialog opened: id=%s url=%s",
                context["definition"].id,
                self._safe_url_for_report(redmine_url),
            )
            self.poll_status_label.setText("Открываю окно Redmine...")
            profile = (
                self.view.page().profile()
                if self.view is not None and self.view.page() is not None
                else None
            )
            dialog = RedmineCreateDialog(
                profile,
                redmine_url,
                ensure_live_monitor_defaults(self.config),
                self,
                self._on_redmine_issue_created,
                list(context["items"]),
                getattr(self, "_pending_redmine_description", ""),
            )
            self.redmine_dialogs.append(dialog)
            dialog.finished.connect(
                lambda _result, d=dialog, current_token=token: self._critical_redmine_dialog_finished(
                    d, current_token
                )
            )
            dialog.show()
            self.poll_status_label.setText("Окно Redmine открыто")
        except Exception:
            self.logger.exception("Critical Redmine dialog preparation failed")
            self._show_guard_message(
                "Redmine",
                "Ошибка подготовки критической задачи Redmine. Подробности записаны в лог.",
            )
            self._finish_critical_flow(token)

    def _critical_redmine_dialog_finished(self, dialog, token: int) -> None:
        try:
            self.redmine_dialogs.remove(dialog)
        except ValueError:
            pass
        context = self._critical_context
        if not context or token != context.get("token"):
            return
        if not context.get("issue_detected"):
            self._finish_critical_flow(token)

    def _on_redmine_issue_created(self, items, issue_number, issue_url):
        if not any(is_critical_problem_item(item) for item in items or []):
            super()._on_redmine_issue_created(items, issue_number, issue_url)
            return

        context = self._critical_context
        if not context:
            self.logger.warning("Critical Redmine callback ignored: context is missing")
            return
        token = context["token"]
        issue_number = str(issue_number or "").strip()
        issue_url = str(issue_url or "").strip()
        item_key = str(getattr((items or [None])[0], "key", "") or "")
        callback_key = (item_key, issue_number, issue_url)
        if callback_key in self._critical_issue_callbacks_seen:
            self.logger.info(
                "Critical Redmine duplicate callback skipped: number=%s url=%s",
                issue_number,
                issue_url,
            )
            return
        self._critical_issue_callbacks_seen.add(callback_key)

        if not issue_number or not issue_url:
            self.logger.warning("Critical Redmine issue callback missing number or URL")
            self._finish_critical_flow(token)
            return

        context["issue_detected"] = True
        self.logger.info(
            "Critical Redmine issue detected: id=%s number=%s url=%s",
            context["definition"].id,
            issue_number,
            issue_url,
        )
        self.poll_status_label.setText(f"Создана задача Redmine #{issue_number}")

        # Critical auto-confirm is mandatory and intentionally ignores the two
        # generic auto-ack checkboxes.  Normal Redmine callbacks still delegate
        # to the base implementation and keep the old settings behavior.
        if not redmine_auto_ack_enabled_for_items(items, self.settings):
            self.logger.error("Critical auto-ack guard unexpectedly returned false")
            self._finish_critical_flow(token)
            return

        comment = build_zabbix_comment(
            issue_number,
            issue_url,
            context.get("analysis"),
        )
        self.logger.info(
            "Critical Zabbix auto-confirm started: id=%s number=%s",
            context["definition"].id,
            issue_number,
        )
        self.poll_status_label.setText(
            "Подтверждаю критический триггер в Zabbix..."
        )
        self._process_zabbix_comments(
            items or [],
            comment,
            acknowledge_missing=True,
            progress_prefix="Подтверждаю критический триггер в Zabbix",
            summary_prefix="Подтверждение критического триггера Zabbix",
            final_error_text=(
                "Задача Redmine создана, но подтверждение критического триггера "
                "в Zabbix завершилось с ошибками. Подробности в логах."
            ),
        )
        QTimer.singleShot(
            400,
            lambda current_token=token: self._wait_for_critical_ack_completion(
                current_token
            ),
        )

    def _wait_for_critical_ack_completion(self, token: int) -> None:
        context = self._critical_context
        if not context or token != context.get("token"):
            return
        workers = getattr(self, "_zbx_workers", {}) or {}
        queue = getattr(self, "_zbx_queue", []) or []
        if workers or queue:
            QTimer.singleShot(
                400,
                lambda current_token=token: self._wait_for_critical_ack_completion(
                    current_token
                ),
            )
            return
        self.logger.info(
            "Critical Zabbix auto-confirm finished: id=%s",
            context["definition"].id,
        )
        self._finish_critical_flow(token)

    def _finish_critical_flow(self, token: int | None = None) -> None:
        context = self._critical_context
        if token is not None and context and token != context.get("token"):
            return
        self._cleanup_critical_history_view()
        self._critical_action_active = False
        self._critical_context = None

    def closeEvent(self, event):
        self._critical_history_token += 1
        self._finish_critical_flow()
        super().closeEvent(event)
