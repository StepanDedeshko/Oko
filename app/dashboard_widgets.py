from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices, QColor
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView

from app.time_range import add_graph_cache_buster, apply_time_range_to_url
from app.autologin import make_zabbix_login_js
from app.logger import get_logger
from app.webengine_lifecycle import register_web_view, run_javascript_if_alive, safe_delete_web_view


def _resolve_web_colors():
    app = QApplication.instance()
    theme_name = app.property("oko_theme_name") if app else None

    if theme_name in {"light_standard", "white_1"}:
        return {
            "page_bg": "#ffffff",
            "host_bg": "#f5faff" if theme_name == "white_1" else "#f3f4f6",
            "card_bg": "#ffffff",
            "text": "#111827",
            "border": "#b9d7e7" if theme_name == "white_1" else "#d1d5db",
        }

    if theme_name == "dark_1":
        return {
            "page_bg": "#0b0b0b",
            "host_bg": "#070b13",
            "card_bg": "#101722",
            "text": "#e8f0f6",
            "border": "#354458",
        }

    return {
        "page_bg": "#0b0b0b",
        "host_bg": "#0b0b0b",
        "card_bg": "#0b0b0b",
        "text": "#d7e8ff",
        "border": "#0b0b0b",
    }


class GraphCard(QFrame):
    """
    Один график внутри дашборда.
    Один график = одна строка.
    """

    def __init__(self, graph_config, profile, time_range, refresh_seconds, zoom_factor, fit_graphs, min_height, credentials=None):
        super().__init__()

        self.graph_config = graph_config
        self.profile = profile
        self.time_range = time_range
        self.refresh_seconds = refresh_seconds
        self.zoom_factor = float(zoom_factor)
        self.fit_graphs = fit_graphs
        self.credentials = credentials or {}
        self.logger = get_logger()
        self._cleaned_up = False

        self.setObjectName("GraphCard")
        self.initial_view_height = max(260, min(int(min_height), 520))
        self.setFrameShape(QFrame.StyledPanel)
        colors = _resolve_web_colors()
        self.setStyleSheet(
            f"QFrame#GraphCard {{ background: transparent; "
            f"border: 1px solid {colors['border']}; border-radius: 12px; }}"
        )

        self.title = QLabel(graph_config.get("title", "График"))
        self.title.setObjectName("GraphTitle")
        self.title.setWordWrap(True)

        self.open_button = QPushButton("Открыть в Zabbix")
        self.open_button.setObjectName("GraphOpenButton")
        self.open_button.setToolTip("Открыть этот график во внешнем браузере")
        self.open_button.clicked.connect(self.open_in_external_browser)

        self.view = register_web_view(QWebEngineView())
        self.view.setObjectName("GraphWebView")
        self.view.setAttribute(Qt.WA_TranslucentBackground, False)
        self.view.setZoomFactor(self.zoom_factor)
        self.view.setFixedHeight(self.initial_view_height)
        self.view.setStyleSheet("background: transparent; border: 0;")

        self.graph_web_container = QFrame()
        self.graph_web_container.setObjectName("GraphWebContainer")
        self.graph_web_container.setAttribute(Qt.WA_TranslucentBackground, False)
        self.graph_web_container.setAutoFillBackground(False)
        self.graph_web_container.setStyleSheet(
            "QFrame#GraphWebContainer { background: transparent; border: 0px; }"
        )
        self.graph_web_container.setFixedHeight(self.initial_view_height)
        web_layout = QVBoxLayout(self.graph_web_container)
        web_layout.setContentsMargins(0, 0, 0, 0)
        web_layout.setSpacing(0)

        self.page = QWebEnginePage(self.profile, self.view)
        self.view.setPage(self.page)
        self.view.loadFinished.connect(self.on_load_finished)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        layout.addWidget(self.title)
        self.duty_trigger_status_label = QLabel("")
        self.duty_trigger_status_label.setWordWrap(True)
        self.duty_trigger_status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.duty_trigger_status_label.setVisible(False)
        self.duty_trigger_status_label.setObjectName("DutyTriggerStatus")

        layout.addWidget(self.open_button)
        web_layout.addWidget(self.view)
        layout.addWidget(self.graph_web_container)
        layout.addWidget(self.duty_trigger_status_label)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.reload)
        self.timer.start(self.refresh_seconds * 1000)

        self.load()

    def build_url(self):
        url = self.graph_config.get("url", "")

        if self.graph_config.get("use_time_range", True):
            return apply_time_range_to_url(url, self.time_range)

        return url

    def build_open_url(self):
        open_url = (
            self.graph_config.get("open_url")
            or self.graph_config.get("zabbix_url")
            or self.graph_config.get("external_url")
            or ""
        ).strip()

        return open_url if open_url else self.build_url()

    def load(self):
        if self._cleaned_up or self.view is None:
            return
        self.view.load(QUrl(self.build_url()))

    def reload(self):
        if self._cleaned_up or self.view is None:
            return
        self.view.reload()

    def refresh_graph(self):
        if self._cleaned_up or self.view is None:
            return
        self.view.load(QUrl(add_graph_cache_buster(self.build_url())))

    def open_in_external_browser(self):
        QDesktopServices.openUrl(QUrl(self.build_open_url()))

    def set_time_range(self, range_value):
        self.time_range = range_value
        self.load()

    def set_duty_trigger_status(self, status: str, message: str):
        status = str(status or "").strip().upper()
        message = str(message or "").strip()
        fallback_messages = {
            "OK": "Сработки поступают все в пределах нормы",
            "ALERT": "Обнаружено отсутствие сработок",
            "NO_DATA": "Нет данных для проверки сработок",
            "PARSE_ERROR": "Не удалось прочитать данные проверки сработок",
            "SOURCE_NOT_FOUND": "Источник данных для проверки не найден",
            "TARGET_NOT_FOUND": "Целевой график для проверки не найден",
        }
        icons = {
            "OK": "✓",
            "ALERT": "⚠",
            "NO_DATA": "ℹ",
            "PARSE_ERROR": "⚠",
            "SOURCE_NOT_FOUND": "⚠",
            "TARGET_NOT_FOUND": "⚠",
        }
        colors = {
            "OK": ("#166534", "#dcfce7", "#22c55e"),
            "ALERT": ("#7f1d1d", "#fee2e2", "#ef4444"),
            "NO_DATA": ("#1e3a8a", "#dbeafe", "#60a5fa"),
            "PARSE_ERROR": ("#78350f", "#fef3c7", "#f59e0b"),
            "SOURCE_NOT_FOUND": ("#78350f", "#fef3c7", "#f59e0b"),
            "TARGET_NOT_FOUND": ("#78350f", "#fef3c7", "#f59e0b"),
        }
        text = message or fallback_messages.get(status, "Статус проверки сработок недоступен")
        icon = icons.get(status, "ℹ")
        text_color, bg_color, border_color = colors.get(status, ("#374151", "#f3f4f6", "#9ca3af"))
        self.duty_trigger_status_label.setText(f"{icon} {text}")
        self.duty_trigger_status_label.setStyleSheet(
            "QLabel#DutyTriggerStatus {"
            f"color: {text_color}; background-color: {bg_color}; border: 1px solid {border_color};"
            "border-radius: 6px; padding: 6px 8px; font-size: 13px;"
            "}"
        )
        self.duty_trigger_status_label.setVisible(True)

    def clear_duty_trigger_status(self):
        self.duty_trigger_status_label.clear()
        self.duty_trigger_status_label.setVisible(False)

    def on_load_finished(self, ok):
        if self._cleaned_up or self.view is None or not ok:
            return

        self.inject_auto_login()

        if self.fit_graphs:
            QTimer.singleShot(500, self.inject_fit_script)
            QTimer.singleShot(1500, self.inject_fit_script)
            QTimer.singleShot(2500, self.inject_fit_script)


    def apply_content_height(self, height):
        try:
            height = int(float(height))
        except (TypeError, ValueError):
            return
        height = max(220, min(height, 720))
        self.view.setFixedHeight(height)
        self.graph_web_container.setFixedHeight(height)
        self.updateGeometry()

    def inject_auto_login(self):
        js = make_zabbix_login_js(
            self.credentials.get("login", ""),
            self.credentials.get("password", "")
        )
        if js and not self._cleaned_up and self.view is not None:
            run_javascript_if_alive(self.view, js)

    def inject_fit_script(self):
        if self._cleaned_up or self.view is None:
            return
        js = """
        (function() {
            const styleId = 'dezhurka-graph-fit';
            let style = document.getElementById(styleId);
            if (!style) {
                style = document.createElement('style');
                style.id = styleId;
                document.head.appendChild(style);
            }

            style.textContent = `
                html, body {
                    margin: 0 !important;
                    padding: 0 !important;
                    overflow: hidden !important;
                    min-height: 0 !important;
                    height: auto !important;
                }

                header, nav, footer, .sidebar, .header-title, .filter-container,
                #header, #footer, #sidebar, .server-name, .menu-main {
                    display: none !important;
                }

                img, svg, canvas {
                    max-width: 100% !important;
                    object-fit: contain !important;
                }

                img {
                    width: 100% !important;
                    height: auto !important;
                    display: block !important;
                    margin: 0 auto !important;
                }

                table, tbody, tr, td, div {
                    max-width: 100% !important;
                    box-sizing: border-box !important;
                }
            `;

            function visibleRects(selector) {
                return Array.from(document.querySelectorAll(selector))
                    .map((node) => node.getBoundingClientRect())
                    .filter((rect) => rect.width > 20 && rect.height > 20);
            }
            let visibleUseful = visibleRects('img, svg, canvas');
            if (!visibleUseful.length) {
                visibleUseful = visibleRects('table');
            }
            if (!visibleUseful.length) {
                visibleUseful = visibleRects('[class*=graph], [id*=graph]');
            }
            const bottom = visibleUseful.length
                ? Math.max(...visibleUseful.map((rect) => rect.bottom))
                : Math.min(document.documentElement.scrollHeight || 0, document.body.scrollHeight || 0);
            const height = Math.max(220, Math.min(720, Math.ceil(bottom + 12)));
            document.documentElement.style.height = height + 'px';
            document.body.style.height = height + 'px';
            return height;
        })();
        """
        if not self._cleaned_up and self.view is not None:
            run_javascript_if_alive(self.view, js, self.apply_content_height)

    def pause_refresh(self):
        if getattr(self, "timer", None) is not None:
            self.timer.stop()

    def resume_refresh(self):
        if self._cleaned_up:
            return
        if getattr(self, "timer", None) is not None and not self.timer.isActive():
            self.timer.start(self.refresh_seconds * 1000)

    def cleanup(self):
        if self._cleaned_up:
            return
        self._cleaned_up = True
        title = self.graph_config.get("title", "График")
        self.logger.info("Graph WebView cleanup started: title=%s", title)
        if getattr(self, "timer", None) is not None:
            try:
                self.timer.stop()
                self.timer.deleteLater()
            except RuntimeError:
                pass
            self.timer = None
        view = self.view
        self.view = None
        self.page = None
        safe_delete_web_view(view, logger=self.logger, context=f"GraphCard title={title}", load_handler=self.on_load_finished)
        self.logger.info("Graph WebView cleanup finished: title=%s", title)

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)


class GraphsDashboard(QWidget):
    """
    Дашборд с графиками.
    """

    def __init__(self, dashboard_config, profile, time_range, settings, credentials=None, product_name=""):
        super().__init__()

        self.dashboard_config = dashboard_config
        self.profile = profile
        self.time_range = time_range
        self.settings = settings
        self.credentials = credentials or {}
        self.product_name = product_name
        self.logger = get_logger()
        self.colors = _resolve_web_colors()
        self.graph_cards = []
        self.graph_cards_by_title = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)

        header = QHBoxLayout()
        title = QLabel(dashboard_config.get("name", "Графики"))
        title.setObjectName("PageTitle")
        self.manual_refresh_button = QPushButton("Обновить")
        self.manual_refresh_button.setObjectName("GraphManualRefreshButton")
        self.manual_refresh_button.setToolTip("Перезагрузить графики текущего раздела без изменения выбранного периода")
        self.manual_refresh_button.clicked.connect(self.refresh_graphs)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.manual_refresh_button)
        root.addLayout(header)

        scroll = QScrollArea()
        scroll.setObjectName("GraphScrollArea")
        scroll.setWidgetResizable(True)
        root.addWidget(scroll, stretch=1)

        content = QWidget()
        content.setStyleSheet(f"background-color: {self.colors['host_bg']};")
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)
        self.cards_layout = layout

        refresh_seconds = int(settings.get("graph_refresh_seconds", 300))
        zoom_factor = float(settings.get("web_zoom_factor", 0.85))
        fit_graphs = bool(settings.get("fit_graphs_to_window", True))
        min_height = int(settings.get("graph_card_min_height", 420))
        self.refresh_seconds = refresh_seconds
        self.zoom_factor = zoom_factor
        self.fit_graphs = fit_graphs
        self.min_height = min_height

        self.enabled_graphs = [
            g for g in dashboard_config.get("graphs", [])
            if g.get("enabled", True)
        ]

        for graph in self.enabled_graphs:
            card = GraphCard(
                graph_config=graph,
                profile=profile,
                time_range=time_range,
                refresh_seconds=self.refresh_seconds,
                zoom_factor=self.zoom_factor,
                fit_graphs=self.fit_graphs,
                min_height=self.min_height,
                credentials=self.credentials,
            )
            self.graph_cards.append(card)
            normalized_title = self._normalize_graph_title(graph.get("title", ""))
            if normalized_title and normalized_title not in self.graph_cards_by_title:
                self.graph_cards_by_title[normalized_title] = card
            layout.addWidget(card)

        layout.addStretch(1)

    @staticmethod
    def _normalize_graph_title(title):
        return " ".join(str(title or "").split()).casefold()

    def find_graph_card_by_title(self, title: str):
        normalized = self._normalize_graph_title(title)
        if not normalized:
            return None
        direct = self.graph_cards_by_title.get(normalized)
        if direct is not None:
            return direct
        for card in self.graph_cards:
            if self._normalize_graph_title(card.graph_config.get("title", "")) == normalized:
                return card
        return None

    def set_time_range(self, range_value):
        self.time_range = range_value
        for card in self.graph_cards:
            card.set_time_range(range_value)

    def reload_all(self):
        for card in list(self.graph_cards):
            card.reload()

    def refresh_graphs(self):
        section_name = self.dashboard_config.get("name", "Графики")
        self.logger.info("Product graphs manual refresh requested")
        self.logger.info(
            "Product graphs manual refresh started: product=%s section=%s cards=%s",
            self.product_name,
            section_name,
            len(self.graph_cards),
        )
        for card in list(self.graph_cards):
            if hasattr(card, "refresh_graph"):
                card.refresh_graph()
            else:
                card.reload()
        self.logger.info(
            "Product graphs manual refresh finished: product=%s section=%s",
            self.product_name,
            section_name,
        )

    def pause_refresh(self):
        for card in list(self.graph_cards):
            if hasattr(card, "pause_refresh"):
                card.pause_refresh()

    def resume_refresh(self):
        if not self.graph_cards:
            self.rebuild_graph_cards()
        for card in list(self.graph_cards):
            if hasattr(card, "resume_refresh"):
                card.resume_refresh()

    def rebuild_graph_cards(self):
        self.logger = get_logger()
        self.logger.info("Graph cards cleanup started")
        self.graph_cards.clear()
        self.graph_cards_by_title.clear()
        for graph in self.enabled_graphs:
            card = GraphCard(
                graph_config=graph,
                profile=self.profile,
                time_range=self.time_range,
                refresh_seconds=self.refresh_seconds,
                zoom_factor=self.zoom_factor,
                fit_graphs=self.fit_graphs,
                min_height=self.min_height,
                credentials=self.credentials,
            )
            self.graph_cards.append(card)
            normalized_title = self._normalize_graph_title(graph.get("title", ""))
            if normalized_title and normalized_title not in self.graph_cards_by_title:
                self.graph_cards_by_title[normalized_title] = card
            self.cards_layout.addWidget(card)
        self.cards_layout.addStretch(1)
        self.logger.info("Graph cards cleanup finished: count=%s", len(self.graph_cards))

    def cleanup(self):
        count = len(self.graph_cards)
        self.logger = get_logger()
        self.logger.info("Graph cards cleanup started")
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                if hasattr(widget, "cleanup"):
                    widget.cleanup()
                widget.setParent(None)
                widget.deleteLater()
        self.graph_cards.clear()
        self.graph_cards_by_title.clear()
        self.logger.info("Graph cards cleanup finished: count=%s", count)

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)


class SimplePageDashboard(QWidget):
    """
    Простая страница Zabbix: Проблемы, dashboard_page и прочее.
    Счётчика проблем больше нет.
    """

    def __init__(self, dashboard_config, profile, refresh_seconds, credentials=None):
        super().__init__()

        self.dashboard_config = dashboard_config
        self.profile = profile
        self.credentials = credentials or {}
        self.logger = get_logger()
        self._cleaned_up = False

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        title = QLabel(dashboard_config.get("name", "Страница"))
        title.setObjectName("PageTitle")

        reload_button = QPushButton("Обновить")
        reload_button.clicked.connect(self.reload_all)

        open_external_button = QPushButton("Открыть в браузере")
        open_external_button.clicked.connect(self.open_current_external)

        self.view = register_web_view(QWebEngineView())
        self.view.setObjectName("GraphWebView")
        self.view.setAttribute(Qt.WA_TranslucentBackground, False)
        self.view.setStyleSheet("background: transparent; border: 0;")
        self.page = QWebEnginePage(profile, self.view)
        self.view.setPage(self.page)
        self.view.loadFinished.connect(self.on_page_loaded)

        root.addWidget(title)
        root.addWidget(reload_button)
        root.addWidget(open_external_button)
        root.addWidget(self.view, stretch=1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.reload_all)
        self.timer.start(int(refresh_seconds) * 1000)

        self.view.load(QUrl(dashboard_config.get("url", "")))

    def on_page_loaded(self, ok):
        if ok and not self._cleaned_up and self.view is not None:
            self.inject_auto_login()


    def apply_content_height(self, height):
        try:
            height = int(float(height))
        except (TypeError, ValueError):
            return
        height = max(220, min(height, 720))
        self.view.setFixedHeight(height)
        self.graph_web_container.setFixedHeight(height)
        self.updateGeometry()

    def inject_auto_login(self):
        js = make_zabbix_login_js(
            self.credentials.get("login", ""),
            self.credentials.get("password", "")
        )
        if js and not self._cleaned_up and self.view is not None:
            run_javascript_if_alive(self.view, js)

    def open_current_external(self):
        current_url = self.view.url().toString()
        if current_url:
            QDesktopServices.openUrl(QUrl(current_url))

    def reload_all(self):
        if not self._cleaned_up and self.view is not None:
            self.view.reload()

    def pause_refresh(self):
        if getattr(self, "timer", None) is not None:
            self.timer.stop()

    def resume_refresh(self):
        if self._cleaned_up:
            return
        if getattr(self, "timer", None) is not None and not self.timer.isActive():
            self.timer.start(int(self.timer.interval()))

    def cleanup(self):
        if self._cleaned_up:
            return
        self._cleaned_up = True
        if getattr(self, "timer", None) is not None:
            try:
                self.timer.stop()
                self.timer.deleteLater()
            except RuntimeError:
                pass
            self.timer = None
        view = self.view
        self.view = None
        self.page = None
        safe_delete_web_view(view, logger=self.logger, context=f"SimplePageDashboard {self.dashboard_config.get('name', '')}", load_handler=self.on_page_loaded)

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)


class ModePagesDashboard(QWidget):
    """
    Страница с переключением режимов: Режим 1 / Режим 2.
    """

    def __init__(self, dashboard_config, profile, refresh_seconds, credentials=None):
        super().__init__()

        self.dashboard_config = dashboard_config
        self.profile = profile
        self.credentials = credentials or {}
        self.logger = get_logger()
        self._cleaned_up = False
        self.modes = dashboard_config.get("modes", [])
        self.current_mode_index = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        title = QLabel(dashboard_config.get("name", "Сработки"))
        title.setObjectName("PageTitle")
        root.addWidget(title)

        button_row = QHBoxLayout()

        self.mode_combo = QComboBox()
        for index, mode in enumerate(self.modes):
            self.mode_combo.addItem(mode.get("name", f"Режим {index + 1}"), index)
        self.mode_combo.currentIndexChanged.connect(self.on_mode_changed)

        reload_button = QPushButton("Обновить")
        reload_button.clicked.connect(self.reload_all)

        open_external_button = QPushButton("Открыть в браузере")
        open_external_button.clicked.connect(self.open_current_external)

        button_row.addWidget(QLabel("Режим:"))
        button_row.addWidget(self.mode_combo)
        button_row.addWidget(reload_button)
        button_row.addWidget(open_external_button)
        button_row.addStretch()

        root.addLayout(button_row)

        self.view = register_web_view(QWebEngineView())
        self.view.setObjectName("GraphWebView")
        self.view.setAttribute(Qt.WA_TranslucentBackground, False)
        self.view.setStyleSheet("background: transparent; border: 0;")

        self.page = QWebEnginePage(profile, self.view)
        self.view.setPage(self.page)
        self.view.loadFinished.connect(self.on_page_loaded)
        root.addWidget(self.view, stretch=1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.reload_all)
        self.timer.start(int(refresh_seconds) * 1000)

        self.load_current_mode()

    def get_current_mode(self):
        if not self.modes:
            return None
        if self.current_mode_index < 0 or self.current_mode_index >= len(self.modes):
            self.current_mode_index = 0
        return self.modes[self.current_mode_index]

    def get_current_url(self):
        mode = self.get_current_mode()
        if not mode:
            return ""
        return mode.get("url", "").strip()

    def on_mode_changed(self):
        value = self.mode_combo.currentData()
        self.current_mode_index = value if value is not None else 0
        self.load_current_mode()

    def load_current_mode(self):
        if self._cleaned_up or self.view is None:
            return
        colors = _resolve_web_colors()
        url = self.get_current_url()
        if not url:
            self.view.setHtml(f"""
                <html>
                <body style="background:{colors['page_bg']};color:{colors['text']};font-family:sans-serif;padding:24px;">
                    <h2>Ссылка режима не задана</h2>
                    <p>Открой config.json и укажи URL для выбранного режима:</p>
                    <pre>FacePay → Сработки → modes → url</pre>
                </body>
                </html>
            """)
            return
        self.view.load(QUrl(url))

    def on_page_loaded(self, ok):
        if ok and not self._cleaned_up and self.view is not None:
            self.inject_auto_login()


    def apply_content_height(self, height):
        try:
            height = int(float(height))
        except (TypeError, ValueError):
            return
        height = max(220, min(height, 720))
        self.view.setFixedHeight(height)
        self.graph_web_container.setFixedHeight(height)
        self.updateGeometry()

    def inject_auto_login(self):
        js = make_zabbix_login_js(
            self.credentials.get("login", ""),
            self.credentials.get("password", "")
        )
        if js:
            run_javascript_if_alive(self.view, js)

    def open_current_external(self):
        url = self.view.url().toString() or self.get_current_url()
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def reload_all(self):
        if self._cleaned_up or self.view is None:
            return
        if self.get_current_url():
            self.view.reload()
        else:
            self.load_current_mode()

    def pause_refresh(self):
        if getattr(self, "timer", None) is not None:
            self.timer.stop()

    def resume_refresh(self):
        if self._cleaned_up:
            return
        if getattr(self, "timer", None) is not None and not self.timer.isActive():
            self.timer.start(int(self.timer.interval()))

    def cleanup(self):
        if self._cleaned_up:
            return
        self._cleaned_up = True
        if getattr(self, "timer", None) is not None:
            try:
                self.timer.stop()
                self.timer.deleteLater()
            except RuntimeError:
                pass
            self.timer = None
        view = self.view
        self.view = None
        self.page = None
        safe_delete_web_view(view, logger=self.logger, context=f"ModePagesDashboard {self.dashboard_config.get('name', '')}", load_handler=self.on_page_loaded)

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)


class ProblemPageDashboard(SimplePageDashboard):
    """
    Оставлен как отдельный класс для совместимости с config.json.
    Работает как обычная страница, без счётчика.
    """

    def __init__(self, dashboard_config, profile, refresh_seconds, app_config=None, credentials=None):
        super().__init__(dashboard_config, profile, refresh_seconds, credentials=credentials)
