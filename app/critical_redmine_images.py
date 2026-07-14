from __future__ import annotations

import base64
import json
import re

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMessageBox

from app.live_zabbix import ensure_live_monitor_defaults
from app.live_zabbix_widget import (
    REDMINE_DESCRIPTION_PLACEHOLDER,
    REDMINE_WATCHER_USER_IDS,
    RedmineCreateDialog,
    extract_redmine_issue_from_payload,
)
from app.logger import get_logger
from app.templates import get_redmine_task_template
from app.webengine_lifecycle import register_web_view, run_javascript_if_alive, safe_delete_web_view


CHART_CAPTURE_RETRY_DELAYS_MS = (250, 650, 1200, 2000, 3200)
ATTACHMENT_UPLOAD_POLL_MS = 500
ATTACHMENT_UPLOAD_MAX_POLLS = 36

CHART_IMAGE_EXTRACTION_SCRIPT = r"""
(function() {
  var images = Array.from(document.images || []);
  var image = images.find(function(item) {
    return item && item.complete && item.naturalWidth > 0 && item.naturalHeight > 0;
  });
  if (!image) {
    return JSON.stringify({ok:false, reason:'image_not_ready', image_count:images.length});
  }
  try {
    var canvas = document.createElement('canvas');
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    var context = canvas.getContext('2d');
    context.drawImage(image, 0, 0);
    var dataUrl = canvas.toDataURL('image/png');
    var marker = 'data:image/png;base64,';
    if (dataUrl.indexOf(marker) !== 0) {
      return JSON.stringify({ok:false, reason:'png_data_url_missing'});
    }
    return JSON.stringify({
      ok:true,
      width:image.naturalWidth,
      height:image.naturalHeight,
      data_base64:dataUrl.slice(marker.length)
    });
  } catch (error) {
    return JSON.stringify({ok:false, reason:'canvas_failed', error:String(error || '')});
  }
})();
"""


def _safe_attachment_stem(value: str) -> str:
    result = re.sub(r"[^0-9A-Za-z_-]+", "_", str(value or "").strip())
    return result.strip("_")[:70] or "event"


def _attachment_filename(item, index: int) -> str:
    event_key = (
        getattr(item, "event_id", "")
        or getattr(item, "key", "")
        or "event"
    )
    suffix = "main" if index == 0 else "all_operations"
    return f"oko_critical_{_safe_attachment_stem(event_key)}_{suffix}.png"


def build_critical_redmine_description(context: dict) -> str:
    """Build the user-facing description using attached image filenames only."""
    item = context["item"]
    definition = context["definition"]
    analysis = context["analysis"]
    attachments = list(context.get("chart_attachments") or [])

    trigger_name = str(getattr(item, "trigger_name", "") or "Проблема Zabbix").strip()
    host = str(getattr(item, "host", "") or "узел не определён").strip()
    ip = ""
    for attr in ("host_ip", "ip", "ip_address"):
        ip = str(getattr(item, attr, "") or "").strip()
        if ip:
            break
    if not ip:
        ip = "не найден"

    lines = [
        "Наблюдается критический триггер:",
        trigger_name,
        "",
        f"Узел: {host}",
        f"IP: {ip}",
    ]

    analysis_text = str(getattr(analysis, "analysis_text", "") or "").strip()
    if definition.slow_history_url and analysis_text:
        lines.extend(["", "Результат проверки:", analysis_text])

    for index, attachment in enumerate(attachments):
        filename = str(attachment.get("filename") or "").strip()
        graph_url = str(attachment.get("graph_page_url") or "").strip()
        if not filename:
            continue
        title = "Основной график" if index == 0 else "График запросов по всем операциям"
        lines.extend(["", f"{title}:", f"!{filename}!"])
        if graph_url:
            lines.append(f"Ссылка на исходный график: {graph_url}")

    lines.extend(["", "Просьба проверить и устранить причину возникновения триггера."])
    return "\n".join(lines).strip()


class CriticalRedmineCreateDialog(RedmineCreateDialog):
    """Redmine form that uploads critical chart PNGs before enabling submit."""

    def __init__(
        self,
        profile,
        redmine_url,
        settings,
        parent=None,
        success_callback=None,
        selected_items=None,
        pending_description="",
        pending_attachments=None,
    ):
        self.pending_attachments = [dict(item) for item in (pending_attachments or [])]
        self._attachment_upload_started = False
        self._attachment_upload_complete = not bool(self.pending_attachments)
        self._attachment_upload_polls = 0
        self._attachment_injection_attempts = 0
        super().__init__(
            profile,
            redmine_url,
            settings,
            parent,
            success_callback,
            selected_items,
            pending_description,
        )

    @staticmethod
    def _submit_enabled_script(enabled: bool) -> str:
        disabled = "false" if enabled else "true"
        return f"""
(function() {{
  var buttons = Array.from(document.querySelectorAll(
    'form#issue-form input[type="submit"], form#issue-form button[type="submit"], '
    'form.new_issue input[type="submit"], form.new_issue button[type="submit"]'
  ));
  buttons.forEach(function(button) {{
    button.disabled = {disabled};
    button.setAttribute('data-oko-critical-lock', {json.dumps('0' if enabled else '1')});
  }});
  return JSON.stringify({{ok:true, count:buttons.length}});
}})();
"""

    @staticmethod
    def attachment_injection_script(attachments) -> str:
        payload = json.dumps(
            [
                {
                    "filename": str(item.get("filename") or ""),
                    "data_base64": str(item.get("data_base64") or ""),
                }
                for item in attachments or []
            ],
            ensure_ascii=False,
        )
        return f"""
(function() {{
  var attachments = {payload};
  var input = document.querySelector(
    '#attachments_fields input.file_selector[type="file"], '
    '#attachments_fields input[type="file"], '
    'input.file_selector[type="file"], '
    'input[name="attachments[dummy][file]"], '
    'input[type="file"][name*="attachment"], '
    'input[type="file"]'
  );
  if (!input) return JSON.stringify({{ok:false, reason:'file_input_not_found'}});
  if (typeof DataTransfer === 'undefined' || typeof File === 'undefined') {{
    return JSON.stringify({{ok:false, reason:'file_api_missing'}});
  }}
  try {{
    input.setAttribute('multiple', 'multiple');
    var transfer = new DataTransfer();
    attachments.forEach(function(attachment) {{
      var binary = atob(String(attachment.data_base64 || ''));
      var bytes = new Uint8Array(binary.length);
      for (var index = 0; index < binary.length; index += 1) {{
        bytes[index] = binary.charCodeAt(index);
      }}
      transfer.items.add(new File([bytes], attachment.filename, {{type:'image/png'}}));
    }});
    input.files = transfer.files;
    input.dispatchEvent(new Event('input', {{bubbles:true}}));
    input.dispatchEvent(new Event('change', {{bubbles:true}}));
    return JSON.stringify({{
      ok:input.files.length === attachments.length,
      file_count:input.files.length,
      expected_count:attachments.length,
      input_name:String(input.name || '')
    }});
  }} catch (error) {{
    return JSON.stringify({{ok:false, reason:'file_injection_failed', error:String(error || '')}});
  }}
}})();
"""

    @staticmethod
    def attachment_status_script(filenames) -> str:
        payload = json.dumps([str(value or "") for value in filenames or []], ensure_ascii=False)
        return f"""
(function() {{
  var filenames = {payload};
  var tokenInputs = Array.from(document.querySelectorAll(
    'input[type="hidden"][name*="attachments"][name$="[token]"], '
    'input[type="hidden"][name*="attachment"][name*="token"]'
  )).filter(function(input) {{ return String(input.value || '').trim(); }});
  var filenameInputs = Array.from(document.querySelectorAll(
    'input[type="hidden"][name*="attachments"][name$="[filename]"], '
    'input[type="hidden"][name*="attachment"][name*="filename"]'
  )).map(function(input) {{ return String(input.value || '').trim(); }});
  var fileInputs = Array.from(document.querySelectorAll('input[type="file"]'));
  var selectedNames = [];
  fileInputs.forEach(function(input) {{
    Array.from(input.files || []).forEach(function(file) {{ selectedNames.push(String(file.name || '')); }});
  }});
  var bodyText = String(document.body ? document.body.innerText : '');
  var seenCount = filenames.filter(function(filename) {{
    return filenameInputs.indexOf(filename) !== -1
      || selectedNames.indexOf(filename) !== -1
      || bodyText.indexOf(filename) !== -1;
  }}).length;
  var busy = !!document.querySelector('.ajax-loading, .filedrop .loading, .attachments_fields .loading, .uploading');
  var errorText = Array.from(document.querySelectorAll('.flash.error, .nodata, .errorExplanation, .file-upload-error'))
    .map(function(node) {{ return String(node.innerText || node.textContent || '').trim(); }})
    .filter(Boolean).join(' | ').slice(0, 500);
  return JSON.stringify({{
    ok:true,
    token_count:tokenInputs.length,
    filename_count:filenameInputs.length,
    selected_count:selectedNames.length,
    seen_count:seenCount,
    busy:busy,
    error_text:errorText
  }});
}})();
"""

    def _set_submit_enabled(self, enabled: bool) -> None:
        page = self.view.page() if self.view is not None else None
        if page is not None:
            run_javascript_if_alive(page, self._submit_enabled_script(enabled))

    def _on_create_guard_result(self, result):
        try:
            payload = json.loads(result or "{}")
        except (TypeError, ValueError):
            payload = {}

        issue = extract_redmine_issue_from_payload(payload)
        if issue and not self._issue_detected:
            self._issue_detected = True
            get_logger().info(
                "Redmine issue detected: number=%s url=%s",
                issue["issue_number"],
                issue["issue_url"],
            )
            self.status_label.setText(f"Задача Redmine создана: #{issue['issue_number']}")
            self.status_label.setVisible(True)
            if self.success_callback:
                self.success_callback(
                    list(self.selected_items), issue["issue_number"], issue["issue_url"]
                )
            return

        if payload.get("valid_issue_form"):
            if self.pending_attachments and not self._attachment_upload_complete:
                if not self._attachment_upload_started:
                    self._start_attachment_upload()
                return
            if self.pending_description and not self._description_injected:
                self._start_description_injection()
            else:
                self._set_submit_enabled(True)
                self.status_label.setText("")
                self.status_label.setVisible(False)
            return

        if payload.get("login_required") or payload.get("broken"):
            self._open_redmine_auth_dialog()
            return

        self.status_label.setText(
            "Redmine не открыл форму создания задачи. Проверьте авторизацию Redmine и настройки шаблона."
        )
        self.status_label.setVisible(True)

    def _start_attachment_upload(self) -> None:
        self._attachment_upload_started = True
        self._set_submit_enabled(False)
        self.status_label.setText("Прикрепляю графики Zabbix к задаче Redmine...")
        self.status_label.setVisible(True)
        QTimer.singleShot(0, self._try_attachment_injection)

    def _try_attachment_injection(self) -> None:
        if self._attachment_upload_complete:
            return
        page = self.view.page() if self.view is not None else None
        if page is None:
            return
        self._attachment_injection_attempts += 1
        run_javascript_if_alive(
            page,
            self.attachment_injection_script(self.pending_attachments),
            self._on_attachment_injection_result,
        )

    def _on_attachment_injection_result(self, result) -> None:
        try:
            payload = json.loads(result or "{}")
        except (TypeError, ValueError):
            payload = {}
        if payload.get("ok"):
            self._attachment_upload_polls = 0
            QTimer.singleShot(ATTACHMENT_UPLOAD_POLL_MS, self._poll_attachment_upload)
            return
        if self._attachment_injection_attempts < 5:
            QTimer.singleShot(600, self._try_attachment_injection)
            return
        self._attachment_upload_failed(str(payload.get("reason") or "file_injection_failed"))

    def _poll_attachment_upload(self) -> None:
        if self._attachment_upload_complete:
            return
        page = self.view.page() if self.view is not None else None
        if page is None:
            return
        self._attachment_upload_polls += 1
        filenames = [item.get("filename") for item in self.pending_attachments]
        run_javascript_if_alive(
            page,
            self.attachment_status_script(filenames),
            self._on_attachment_status_result,
        )

    def _on_attachment_status_result(self, result) -> None:
        try:
            payload = json.loads(result or "{}")
        except (TypeError, ValueError):
            payload = {}
        expected = len(self.pending_attachments)
        token_count = int(payload.get("token_count") or 0)
        selected_count = int(payload.get("selected_count") or 0)
        seen_count = int(payload.get("seen_count") or 0)
        busy = bool(payload.get("busy"))

        uploaded = token_count >= expected
        direct_form_ready = selected_count >= expected and seen_count >= expected and not busy
        if uploaded or direct_form_ready:
            self._attachment_upload_complete = True
            get_logger().info(
                "Critical Redmine chart attachments ready: expected=%s tokens=%s selected=%s",
                expected,
                token_count,
                selected_count,
            )
            self.status_label.setText("Графики прикреплены. Вставляю описание задачи...")
            self._start_description_injection()
            return

        error_text = str(payload.get("error_text") or "").strip()
        if error_text:
            self._attachment_upload_failed(error_text)
            return
        if self._attachment_upload_polls >= ATTACHMENT_UPLOAD_MAX_POLLS:
            self._attachment_upload_failed("attachment_upload_timeout")
            return
        QTimer.singleShot(ATTACHMENT_UPLOAD_POLL_MS, self._poll_attachment_upload)

    def _attachment_upload_failed(self, reason: str) -> None:
        get_logger().warning("Critical Redmine attachment upload failed: %s", reason)
        self.status_label.setText(
            "Не удалось прикрепить графики к Redmine. Создание задачи заблокировано, "
            "чтобы она не ушла без изображений. Закройте окно и повторите попытку."
        )
        self.status_label.setVisible(True)
        self._set_submit_enabled(False)

    def _on_description_injection_result(self, result):
        try:
            payload = json.loads(result or "{}")
        except (TypeError, ValueError):
            payload = {}
        if payload.get("ok"):
            self._description_injected = True
            get_logger().info("Critical Redmine description injection success")
            self._set_submit_enabled(True)
            self.status_label.setText("")
            self.status_label.setVisible(False)
            return
        if self._description_injection_attempts >= 4 and not self._description_injected:
            clipboard = QApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(self.pending_description)
            get_logger().warning("Critical Redmine description injection failed")
            self.status_label.setText(
                "Не удалось вставить описание с прикреплёнными графиками. "
                "Создание задачи заблокировано; описание скопировано в буфер обмена."
            )
            self.status_label.setVisible(True)
            self._set_submit_enabled(False)


_ORIGINAL_ANALYSIS_COMPLETE = None
_ORIGINAL_FINISH_FLOW = None


def _decode_chart_result(result) -> dict:
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        try:
            return json.loads(result or "{}")
        except (TypeError, ValueError):
            return {}
    return {}


def _cleanup_critical_chart_view(self) -> None:
    view = getattr(self, "_critical_chart_view", None)
    self._critical_chart_view = None
    if view is not None:
        safe_delete_web_view(view, logger=self.logger, context="CriticalLiveZabbix chart capture")


def _critical_analysis_complete_with_images(self, analysis, token: int) -> None:
    context = self._critical_context
    if not context or token != context.get("token"):
        return
    if context.get("chart_attachments_ready"):
        return _ORIGINAL_ANALYSIS_COMPLETE(self, analysis, token)
    if context.get("chart_capture_started"):
        return

    chart_urls = [str(url or "").strip() for url in (analysis.chart_image_urls or []) if str(url or "").strip()]
    graph_urls = [str(url or "").strip() for url in (analysis.graph_page_urls or [])]
    if not chart_urls:
        self._show_guard_message(
            "Критический триггер",
            "Для критического триггера не задан URL изображения графика. Задача Redmine не подготовлена.",
        )
        self._finish_critical_flow(token)
        return

    context["analysis"] = analysis
    context["chart_capture_started"] = True
    context["chart_capture_index"] = 0
    context["chart_capture_attempt"] = 0
    context["chart_capture_urls"] = chart_urls
    context["chart_graph_urls"] = graph_urls
    context["chart_attachments"] = []
    self.poll_status_label.setText("Критический триггер: получаю изображения графиков...")
    self._critical_capture_next_chart(token)


def _critical_capture_next_chart(self, token: int) -> None:
    context = self._critical_context
    if not context or token != context.get("token"):
        return
    self._cleanup_critical_chart_view()
    index = int(context.get("chart_capture_index", 0))
    urls = list(context.get("chart_capture_urls") or [])
    if index >= len(urls):
        context["chart_attachments_ready"] = True
        self.logger.info(
            "Critical chart capture completed: id=%s attachments=%s",
            context["definition"].id,
            len(context.get("chart_attachments") or []),
        )
        return _ORIGINAL_ANALYSIS_COMPLETE(self, context["analysis"], token)

    profile = self.view.page().profile() if self.view is not None and self.view.page() is not None else None
    if profile is None:
        self._critical_chart_capture_failed(token, "shared_profile_missing")
        return

    view = register_web_view(QWebEngineView(self))
    view.setPage(QWebEnginePage(profile, view))
    view.hide()
    self._critical_chart_view = view
    context["chart_capture_attempt"] = 0
    view.loadFinished.connect(
        lambda ok, current_token=token, current_index=index: self._critical_chart_loaded(
            bool(ok), current_token, current_index
        )
    )
    self.logger.info(
        "Critical chart capture started: id=%s index=%s url=%s",
        context["definition"].id,
        index,
        self._safe_url_for_report(urls[index]),
    )
    view.load(QUrl(urls[index]))


def _critical_chart_loaded(self, ok: bool, token: int, index: int) -> None:
    context = self._critical_context
    if not context or token != context.get("token") or index != context.get("chart_capture_index"):
        return
    if not ok:
        self._critical_chart_capture_failed(token, "load_finished_false")
        return
    QTimer.singleShot(250, lambda: self._critical_try_extract_chart(token, index))


def _critical_try_extract_chart(self, token: int, index: int) -> None:
    context = self._critical_context
    if not context or token != context.get("token") or index != context.get("chart_capture_index"):
        return
    view = getattr(self, "_critical_chart_view", None)
    page = view.page() if view is not None else None
    if page is None:
        self._critical_chart_capture_failed(token, "chart_page_missing")
        return
    context["chart_capture_attempt"] = int(context.get("chart_capture_attempt", 0)) + 1
    run_javascript_if_alive(
        page,
        CHART_IMAGE_EXTRACTION_SCRIPT,
        lambda result, current_token=token, current_index=index: self._critical_chart_result(
            result, current_token, current_index
        ),
    )


def _critical_chart_result(self, result, token: int, index: int) -> None:
    context = self._critical_context
    if not context or token != context.get("token") or index != context.get("chart_capture_index"):
        return
    payload = _decode_chart_result(result)
    data_base64 = str(payload.get("data_base64") or "")
    if payload.get("ok") and data_base64:
        try:
            decoded = base64.b64decode(data_base64, validate=True)
        except Exception:
            decoded = b""
        if len(decoded) < 100:
            self._critical_chart_capture_failed(token, "captured_png_too_small")
            return
        item = context["item"]
        graph_urls = list(context.get("chart_graph_urls") or [])
        context["chart_attachments"].append(
            {
                "filename": _attachment_filename(item, index),
                "data_base64": data_base64,
                "graph_page_url": graph_urls[index] if index < len(graph_urls) else "",
                "width": int(payload.get("width") or 0),
                "height": int(payload.get("height") or 0),
            }
        )
        context["chart_capture_index"] = index + 1
        self._critical_capture_next_chart(token)
        return

    attempt = int(context.get("chart_capture_attempt", 0))
    if attempt <= len(CHART_CAPTURE_RETRY_DELAYS_MS):
        delay = CHART_CAPTURE_RETRY_DELAYS_MS[attempt - 1]
        QTimer.singleShot(delay, lambda: self._critical_try_extract_chart(token, index))
        return
    self._critical_chart_capture_failed(token, str(payload.get("reason") or "image_not_ready"))


def _critical_chart_capture_failed(self, token: int, reason: str) -> None:
    context = self._critical_context
    if not context or token != context.get("token"):
        return
    self.logger.warning(
        "Critical chart capture failed: id=%s reason=%s",
        context["definition"].id,
        reason,
    )
    self._cleanup_critical_chart_view()
    self._show_guard_message(
        "Критический триггер",
        "Не удалось получить изображение графика Zabbix. Задача Redmine не открыта, "
        "чтобы не создать её без обязательной картинки.",
    )
    self._finish_critical_flow(token)


def _open_critical_redmine_dialog_with_images(self, token: int) -> None:
    context = self._critical_context
    if not context or token != context.get("token"):
        return
    attachments = list(context.get("chart_attachments") or [])
    if not attachments:
        self._critical_chart_capture_failed(token, "attachments_missing")
        return

    try:
        template = get_redmine_task_template(self.config, special=True)
        create_url = str(template.get("create_url") or "").strip()
        if not create_url:
            self._show_guard_message(
                "Redmine",
                "URL создания задачи Redmine не задан в настройках специального шаблона.",
            )
            self._finish_critical_flow(token)
            return

        item = context["item"]
        subject = self._redmine_subject([item])
        description = build_critical_redmine_description(context)
        default_params = {
            "issue[tracker_id]": str(template.get("tracker_id") or "32"),
            "issue[assigned_to_id]": str(template.get("assigned_to_id") or "1121"),
            "issue[custom_field_values][94]": str(template.get("custom_field_94") or "Не применим"),
            "issue[watcher_user_ids][]": REDMINE_WATCHER_USER_IDS,
        }
        if template.get("priority_id"):
            default_params["issue[priority_id]"] = str(template.get("priority_id"))

        redmine_url = self._merge_redmine_url_params(
            create_url,
            {
                "issue[subject]": subject,
                "issue[description]": REDMINE_DESCRIPTION_PLACEHOLDER,
            },
            default_params,
        )
        self._pending_redmine_description = description
        profile = self.view.page().profile() if self.view is not None and self.view.page() is not None else None
        dialog = CriticalRedmineCreateDialog(
            profile,
            redmine_url,
            ensure_live_monitor_defaults(self.config),
            self,
            self._on_redmine_issue_created,
            list(context["items"]),
            description,
            attachments,
        )
        self.redmine_dialogs.append(dialog)
        dialog.finished.connect(
            lambda _result, d=dialog, current_token=token: self._critical_redmine_dialog_finished(
                d, current_token
            )
        )
        dialog.show()
        self.poll_status_label.setText("Окно Redmine открыто — прикрепляю графики...")
        self.logger.info(
            "Critical Redmine dialog opened with chart attachments: id=%s attachments=%s",
            context["definition"].id,
            len(attachments),
        )
    except Exception:
        self.logger.exception("Critical Redmine dialog with attachments failed")
        self._show_guard_message(
            "Redmine",
            "Ошибка подготовки критической задачи Redmine с изображениями. Подробности записаны в лог.",
        )
        self._finish_critical_flow(token)


def _finish_critical_flow_with_chart_cleanup(self, token=None) -> None:
    self._cleanup_critical_chart_view()
    return _ORIGINAL_FINISH_FLOW(self, token)


def install_critical_redmine_images() -> bool:
    """Install the image-attachment critical flow before MainWindow is created."""
    global _ORIGINAL_ANALYSIS_COMPLETE, _ORIGINAL_FINISH_FLOW

    import app.critical_live_zabbix_widget as critical_widget

    cls = critical_widget.CriticalLiveZabbixMonitorWidget
    if getattr(cls, "_critical_redmine_images_installed", False):
        return False

    _ORIGINAL_ANALYSIS_COMPLETE = cls._critical_analysis_complete
    _ORIGINAL_FINISH_FLOW = cls._finish_critical_flow

    cls._cleanup_critical_chart_view = _cleanup_critical_chart_view
    cls._critical_capture_next_chart = _critical_capture_next_chart
    cls._critical_chart_loaded = _critical_chart_loaded
    cls._critical_try_extract_chart = _critical_try_extract_chart
    cls._critical_chart_result = _critical_chart_result
    cls._critical_chart_capture_failed = _critical_chart_capture_failed
    cls._critical_analysis_complete = _critical_analysis_complete_with_images
    cls._open_critical_redmine_dialog = _open_critical_redmine_dialog_with_images
    cls._finish_critical_flow = _finish_critical_flow_with_chart_cleanup
    cls._critical_redmine_images_installed = True
    return True
