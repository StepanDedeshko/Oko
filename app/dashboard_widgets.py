from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QColor
from PySide6.QtWidgets import (
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

from app.time_range import apply_time_range_to_url
from app.autologin import make_zabbix_login_js


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

        self.setObjectName("GraphCard")
        self.setMinimumHeight(int(min_height))
        self.setFrameShape(QFrame.StyledPanel)

        self.title = QLabel(graph_config.get("title", "График"))
        self.title.setObjectName("PageTitle")
        self.title.setWordWrap(True)

        self.open_button = QPushButton("Открыть в Zabbix")
        self.open_button.setToolTip("Открыть этот график во внешнем браузере")
        self.open_button.clicked.connect(self.open_in_external_browser)

        self.view = QWebEngineView()
        self.view.setZoomFactor(self.zoom_factor)
        self.view.setStyleSheet("background-color: #0b0b0b; border: 0;")

        self.page = QWebEnginePage(self.profile, self.view)
        try:
            self.page.setBackgroundColor(QColor("#0b0b0b"))
        except Exception:
            pass

        self.view.setPage(self.page)
        self.view.loadFinished.connect(self.on_load_finished)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        layout.addWidget(self.title)
        layout.addWidget(self.open_button)
        layout.addWidget(self.view, stretch=1)

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
        self.view.load(QUrl(self.build_url()))

    def reload(self):
        self.view.reload()

    def open_in_external_browser(self):
        QDesktopServices.openUrl(QUrl(self.build_open_url()))

    def set_time_range(self, range_value):
        self.time_range = range_value
        self.load()

    def on_load_finished(self, ok):
        if not ok:
            return

        self.inject_auto_login()

        if self.fit_graphs:
            QTimer.singleShot(500, self.inject_fit_script)
            QTimer.singleShot(1500, self.inject_fit_script)

    def inject_auto_login(self):
        js = make_zabbix_login_js(
            self.credentials.get("login", ""),
            self.credentials.get("password", "")
        )
        if js:
            self.view.page().runJavaScript(js)

    def inject_fit_script(self):
        js = r"""
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
                    overflow-x: hidden !important;
                    overflow-y: auto !important;
                    background: #0b0b0b !important;
                }

                body * {
                    background-color: transparent !important;
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

            document.body.style.background = '#0b0b0b';
            document.documentElement.style.background = '#0b0b0b';
            return 'OK';
        })();
        """
        self.view.page().runJavaScript(js)


class GraphsDashboard(QWidget):
    """
    Дашборд с графиками.
    """

    def __init__(self, dashboard_config, profile, time_range, settings, credentials=None):
        super().__init__()

        self.dashboard_config = dashboard_config
        self.profile = profile
        self.time_range = time_range
        self.settings = settings
        self.credentials = credentials or {}
        self.graph_cards = []

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)

        title = QLabel(dashboard_config.get("name", "Графики"))
        title.setObjectName("PageTitle")
        root.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        root.addWidget(scroll, stretch=1)

        content = QWidget()
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)

        refresh_seconds = int(settings.get("graph_refresh_seconds", 300))
        zoom_factor = float(settings.get("web_zoom_factor", 0.85))
        fit_graphs = bool(settings.get("fit_graphs_to_window", True))
        min_height = int(settings.get("graph_card_min_height", 420))

        enabled_graphs = [
            g for g in dashboard_config.get("graphs", [])
            if g.get("enabled", True)
        ]

        for graph in enabled_graphs:
            card = GraphCard(
                graph_config=graph,
                profile=profile,
                time_range=time_range,
                refresh_seconds=refresh_seconds,
                zoom_factor=zoom_factor,
                fit_graphs=fit_graphs,
                min_height=min_height,
                credentials=self.credentials,
            )
            self.graph_cards.append(card)
            layout.addWidget(card)

        layout.addStretch(1)

    def set_time_range(self, range_value):
        self.time_range = range_value
        for card in self.graph_cards:
            card.set_time_range(range_value)

    def reload_all(self):
        for card in self.graph_cards:
            card.reload()


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

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        title = QLabel(dashboard_config.get("name", "Страница"))
        title.setObjectName("PageTitle")

        reload_button = QPushButton("Обновить")
        reload_button.clicked.connect(self.reload_all)

        open_external_button = QPushButton("Открыть в браузере")
        open_external_button.clicked.connect(self.open_current_external)

        self.view = QWebEngineView()
        self.view.setStyleSheet("background-color: #0b0b0b; border: 0;")
        self.page = QWebEnginePage(profile, self.view)
        try:
            self.page.setBackgroundColor(QColor("#0b0b0b"))
        except Exception:
            pass

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
        if ok:
            self.inject_auto_login()

    def inject_auto_login(self):
        js = make_zabbix_login_js(
            self.credentials.get("login", ""),
            self.credentials.get("password", "")
        )
        if js:
            self.view.page().runJavaScript(js)

    def open_current_external(self):
        current_url = self.view.url().toString()
        if current_url:
            QDesktopServices.openUrl(QUrl(current_url))

    def reload_all(self):
        self.view.reload()


class ModePagesDashboard(QWidget):
    """
    Страница с переключением режимов: Режим 1 / Режим 2.
    """

    def __init__(self, dashboard_config, profile, refresh_seconds, credentials=None):
        super().__init__()

        self.dashboard_config = dashboard_config
        self.profile = profile
        self.credentials = credentials or {}
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

        self.view = QWebEngineView()
        self.view.setStyleSheet("background-color: #0b0b0b; border: 0;")

        self.page = QWebEnginePage(profile, self.view)
        try:
            self.page.setBackgroundColor(QColor("#0b0b0b"))
        except Exception:
            pass

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
        url = self.get_current_url()
        if not url:
            self.view.setHtml("""
                <html>
                <body style="background:#0b0b0b;color:#d7e8ff;font-family:sans-serif;padding:24px;">
                    <h2>Ссылка режима не задана</h2>
                    <p>Открой config.json и укажи URL для выбранного режима:</p>
                    <pre>FacePay → Сработки → modes → url</pre>
                </body>
                </html>
            """)
            return
        self.view.load(QUrl(url))

    def on_page_loaded(self, ok):
        if ok:
            self.inject_auto_login()

    def inject_auto_login(self):
        js = make_zabbix_login_js(
            self.credentials.get("login", ""),
            self.credentials.get("password", "")
        )
        if js:
            self.view.page().runJavaScript(js)

    def open_current_external(self):
        url = self.view.url().toString() or self.get_current_url()
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def reload_all(self):
        if self.get_current_url():
            self.view.reload()
        else:
            self.load_current_mode()


class ProblemPageDashboard(SimplePageDashboard):
    """
    Оставлен как отдельный класс для совместимости с config.json.
    Работает как обычная страница, без счётчика.
    """

    def __init__(self, dashboard_config, profile, refresh_seconds, app_config=None, credentials=None):
        super().__init__(dashboard_config, profile, refresh_seconds, credentials=credentials)
