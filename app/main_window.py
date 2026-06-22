from datetime import datetime
import subprocess
from pathlib import Path

from PySide6.QtCore import QRect, QTimer, Qt, QUrl
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QComboBox,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QToolBar,
    QWidget,
    QVBoxLayout,
    QSizePolicy,
)
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView

from app.duty_mode import DutyModeWidget
from app.home_config import AppSettingsWidget, HomePageWidget
from app.config import save_config
from app.dashboard_widgets import GraphsDashboard, ProblemPageDashboard, SimplePageDashboard, ModePagesDashboard
from app.hotkeys_widget import HotkeysWidget
from app.system_info_widget import SystemInfoWidget
from app.zabbix_profile import create_profile
from app.system_metrics import SystemMetricsProvider
from app.theme import apply_theme
from app.theme_logo import load_theme_logo
from app.app_info import APP_NAME
from app.logger import get_logger
from app.screen_utils import clamp_rect_to_available, rect_fits_available, safe_window_size
from app.webengine_lifecycle import current_rss_mb, register_web_view, safe_delete_web_view, tracked_web_view_count


class MainWindow(QMainWindow):
    """
    Интерфейс без боковой шторки.

    Верхняя панель:
    - Главная страница;
    - Настройки;
    - продукт;
    - раздел;
    - период графиков.

    Логика:
    выбираем продукт -> выбираем раздел -> открывается нужный экран.
    """

    def __init__(self, config, credentials):
        super().__init__()

        self.config = config
        self.credentials = credentials
        self.settings = config.get("settings", {})
        self.current_time_range = self.settings.get("default_time_range", "1h")

        self.profiles = {}
        self.dashboard_widgets = []
        self.graph_dashboards = []
        self.duty_mode_widget = None
        self.home_page_widget = None
        self.home_page_index = None
        self.page_has_time_buttons = {}
        self.product_dashboard_indexes = {}
        self.settings_page_index = None
        self.hotkeys_page_index = None
        self.system_info_page_index = None
        self.auth_page_index = None
        self.auth_web_views = []
        self._last_memory_warning = False

        self.is_updating_selectors = False
        self.metrics_provider = SystemMetricsProvider()
        self.loading_screen = None
        self.problem_counter_ready = False
        self.current_problem_loading_widget = None
        self.problem_loading_active = False
        self.logger = get_logger()

        self.setWindowTitle(APP_NAME)
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowCloseButtonHint
        )

        self.stack = QStackedWidget()

        self.main_container = QWidget()
        self.main_layout = QVBoxLayout(self.main_container)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        self.main_layout.addWidget(self.stack, stretch=1)

        self.create_bottom_hud()
        self.setCentralWidget(self.main_container)

        self.create_profiles()
        self.create_toolbar()
        self.create_shortcuts()

        self.create_auth_pages()
        self.create_settings_page()
        self.create_hotkeys_page()
        self.create_system_info_page()
        self.create_dashboard_pages()
        self.create_home_page()
        self.create_duty_mode_page()
        self.populate_product_combo()
        self.select_first_dashboard()

        self.apply_initial_window_mode()

    def create_bottom_hud(self):
        """
        Нижняя HUD-панель с локальными показателями устройства.
        """
        self.bottom_hud = QWidget()
        self.bottom_hud.setObjectName("BottomHud")

        layout = QHBoxLayout(self.bottom_hud)
        layout.setContentsMargins(14, 6, 14, 6)
        layout.setSpacing(18)

        self.cpu_temp_label = QLabel("CPU temp.: н/д")
        self.memory_label = QLabel("Память: н/д")
        self.network_label = QLabel("Сеть: н/д")
        self.updated_label = QLabel("Данные обновлены: --:--:--")

        layout.addWidget(self.cpu_temp_label)
        layout.addWidget(self.memory_label)
        layout.addWidget(self.network_label)
        layout.addStretch()
        layout.addWidget(self.updated_label)

        self.main_layout.addWidget(self.bottom_hud)

        self.metrics_timer = QTimer(self)
        self.metrics_timer.timeout.connect(self.update_bottom_hud)
        self.metrics_timer.start(2000)

        self.memory_diagnostics_timer = QTimer(self)
        self.memory_diagnostics_timer.timeout.connect(self.log_memory_status)
        self.memory_diagnostics_timer.start(60000)

        self.update_bottom_hud()
        self.log_memory_status()

    def update_bottom_hud(self):
        metrics = self.metrics_provider.get_metrics()

        self.cpu_temp_label.setText(f"🌡 CPU temp.: {metrics['cpu_temp']}")
        self.memory_label.setText(f"▣ Память: {metrics['memory']}")
        self.network_label.setText(f"⇅ Сеть: {metrics['network']}")
        self.updated_label.setText(
            "⟳ Данные обновлены: " + datetime.now().strftime("%H:%M:%S")
        )

    def create_profiles(self):
        for instance in self.config.get("zabbix_instances", []):
            if not instance.get("enabled", True):
                continue

            zabbix_id = instance.get("id")
            self.profiles[zabbix_id] = create_profile(zabbix_id)

    def create_toolbar(self):
        self.toolbar = QToolBar("Панель")
        self.toolbar.setMovable(False)
        self.addToolBar(self.toolbar)

        self.product_combo = QComboBox()
        self.configure_toolbar_combo(self.product_combo, 120, 260)
        self.product_combo.currentIndexChanged.connect(self.on_product_changed)
        self.product_combo.activated.connect(self.on_product_changed)

        self.section_combo = QComboBox()
        self.configure_toolbar_combo(self.section_combo, 120, 260)
        self.section_combo.currentIndexChanged.connect(self.on_section_changed)
        self.section_combo.activated.connect(self.on_section_changed)

        self.time_combo = QComboBox()
        self.configure_toolbar_combo(self.time_combo, 100, 180)
        for item in self.config.get("time_ranges", []):
            self.time_combo.addItem(item.get("title", ""), item.get("value", ""))

        # Выбираем текущий период из config.
        for i in range(self.time_combo.count()):
            if self.time_combo.itemData(i) == self.current_time_range:
                self.time_combo.setCurrentIndex(i)
                break

        self.time_combo.currentIndexChanged.connect(self.on_time_changed)

        self.home_button = QPushButton("Главная страница")
        self.home_button.setToolTip("Открыть главную страницу")
        self.home_button.clicked.connect(self.open_home_page)

        self.theme_logo_label = QLabel()
        self.theme_logo_label.setObjectName("ThemeLogo")
        self.theme_logo_label.setFixedSize(34, 34)
        self.theme_logo_label.setAlignment(Qt.AlignCenter)
        self.theme_logo_label.setToolTip("Открыть главную страницу")
        self.theme_logo_label.mousePressEvent = lambda event: self.open_home_page()
        self.update_theme_logo()

        app_title = QLabel(f"  {APP_NAME}  ")
        app_title.setObjectName("AppTitle")
        app_title.setToolTip("Открыть главную страницу")
        app_title.mousePressEvent = lambda event: self.open_home_page()

        self.toolbar.addWidget(self.theme_logo_label)
        self.toolbar.addWidget(app_title)
        self.toolbar.addWidget(self.home_button)
        self.toolbar.addSeparator()

        self.toolbar.addWidget(QLabel("Продукт: "))
        self.toolbar.addWidget(self.product_combo)
        self.toolbar.addSeparator()

        self.toolbar.addWidget(QLabel("Раздел: "))
        self.toolbar.addWidget(self.section_combo)
        self.toolbar.addSeparator()

        self.time_label_action = self.toolbar.addWidget(QLabel("Период: "))
        self.time_combo_action = self.toolbar.addWidget(self.time_combo)
        self.toolbar.addSeparator()

    def configure_toolbar_combo(self, combo, minimum_width, maximum_width):
        combo.setMinimumWidth(minimum_width)
        combo.setMaximumWidth(maximum_width)
        combo.setMinimumContentsLength(12)
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        combo.view().setTextElideMode(Qt.ElideRight)


    def create_shortcuts(self):
        QShortcut(QKeySequence("F11"), self).activated.connect(self.toggle_fullscreen)
        QShortcut(QKeySequence("Esc"), self).activated.connect(self.exit_fullscreen)
        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(self.reload_current)
        QShortcut(QKeySequence("F5"), self).activated.connect(self.reload_current)

    def create_auth_pages(self):
        """
        Служебная авторизация.
        Она не показывается в списках, но нужна для создания web-сессий Zabbix.
        """
        container = QWidget()
        layout = QVBoxLayout(container)

        label = QLabel(
            "Служебная авторизация. Обычно этот экран не нужен пользователю."
        )
        label.setWordWrap(True)
        layout.addWidget(label)

        # Используем вкладки только внутри скрытого служебного экрана.
        from PySide6.QtWidgets import QTabWidget
        auth_tabs = QTabWidget()
        layout.addWidget(auth_tabs, stretch=1)

        for instance in self.config.get("zabbix_instances", []):
            if not instance.get("enabled", True):
                continue

            zabbix_id = instance.get("id")
            name = instance.get("name", zabbix_id)
            login_url = instance.get("login_url")
            profile = self.profiles.get(zabbix_id)
            creds = self.credentials.get(zabbix_id, {})

            view = register_web_view(QWebEngineView())
            page = QWebEnginePage(profile, view)
            view.setPage(page)
            view.loadFinished.connect(lambda ok, v=view, c=creds: self.inject_login(v, c))
            view.load(QUrl(login_url))

            self.auth_web_views.append((view, page))
            auth_tabs.addTab(view, name)

        self.auth_page_index = self.stack.addWidget(container)
        self.page_has_time_buttons[self.auth_page_index] = False

    def create_settings_page(self):
        settings_widget = AppSettingsWidget(config=self.config)

        self.settings_page_index = self.stack.addWidget(settings_widget)
        self.page_has_time_buttons[self.settings_page_index] = False

    def create_hotkeys_page(self):
        hotkeys_widget = HotkeysWidget()

        self.hotkeys_page_index = self.stack.addWidget(hotkeys_widget)
        self.page_has_time_buttons[self.hotkeys_page_index] = False

    def open_hotkeys_settings(self):
        if self.hotkeys_page_index is not None:
            self.stack.setCurrentIndex(self.hotkeys_page_index)
            self.set_time_selector_visible(False)

    def update_theme_logo(self):
        theme_name = self.settings.get("theme", "mass_effect")
        pixmap = load_theme_logo(theme_name, size=30)

        if not pixmap.isNull():
            self.theme_logo_label.setPixmap(pixmap)
        else:
            self.theme_logo_label.clear()

    def change_theme(self, theme_name):
        self.settings["theme"] = theme_name
        self.config["settings"] = self.settings
        save_config(self.config)
        app = QGuiApplication.instance()
        apply_theme(app, theme_name)
        self.update_theme_logo()

    def create_system_info_page(self):
        system_info_widget = SystemInfoWidget()

        self.system_info_page_index = self.stack.addWidget(system_info_widget)
        self.page_has_time_buttons[self.system_info_page_index] = False

    def open_system_info(self):
        if self.system_info_page_index is not None:
            widget = self.stack.widget(self.system_info_page_index)
            if hasattr(widget, "refresh"):
                widget.refresh()

            self.stack.setCurrentIndex(self.system_info_page_index)
            self.set_time_selector_visible(False)
            self.pause_inactive_web_dashboards()

    def create_dashboard_pages(self):
        self.product_dashboard_indexes = {}

        for product_index, product in enumerate(self.config.get("products", [])):
            if not product.get("enabled", True):
                continue

            product_name = product.get("name", f"Продукт {product_index + 1}")
            self.product_dashboard_indexes[product_name] = []

            for dashboard_index, dashboard in enumerate(product.get("dashboards", [])):
                if not dashboard.get("enabled", True):
                    continue

                zabbix_id = dashboard.get("zabbix_id")
                profile = self.profiles.get(zabbix_id)

                if profile is None:
                    widget = QLabel(f"Не найден Zabbix profile: {zabbix_id}")
                    has_time = False
                elif dashboard.get("type") == "graphs_grid":
                    widget = GraphsDashboard(
                        dashboard_config=dashboard,
                        profile=profile,
                        time_range=self.current_time_range,
                        settings=self.settings,
                        credentials=self.credentials.get(zabbix_id, {}),
                        product_name=product_name,
                    )
                    self.graph_dashboards.append(widget)
                    has_time = True
                elif dashboard.get("type") == "problems_page":
                    widget = ProblemPageDashboard(
                        dashboard_config=dashboard,
                        profile=profile,
                        refresh_seconds=self.settings.get("problems_refresh_seconds", 60),
                        app_config=self.config,
                        credentials=self.credentials.get(zabbix_id, {})
                    )
                    has_time = False
                elif dashboard.get("type") == "dashboard_page":
                    widget = SimplePageDashboard(
                        dashboard_config=dashboard,
                        profile=profile,
                        refresh_seconds=self.settings.get("graph_refresh_seconds", 300),
                        credentials=self.credentials.get(zabbix_id, {})
                    )
                    has_time = False
                elif dashboard.get("type") == "mode_pages":
                    widget = ModePagesDashboard(
                        dashboard_config=dashboard,
                        profile=profile,
                        refresh_seconds=self.settings.get("graph_refresh_seconds", 300),
                        credentials=self.credentials.get(zabbix_id, {})
                    )
                    has_time = False
                else:
                    widget = QLabel(f"Неизвестный тип дашборда: {dashboard.get('type')}")
                    has_time = False

                index = self.stack.addWidget(widget)
                self.dashboard_widgets.append(widget)
                self.page_has_time_buttons[index] = has_time

                self.product_dashboard_indexes[product_name].append({
                    "name": dashboard.get("name", f"Раздел {dashboard_index + 1}"),
                    "index": index,
                    "has_time": has_time,
                    "type": dashboard.get("type"),
                    "widget": widget,
                })



    def create_home_page(self):
        """
        Главная страница не отображается в списке продуктов.
        Она открывается кликом по логотипу/названию приложения.
        """
        self.home_page_widget = HomePageWidget(
            config=self.config,
            open_duty_callback=self.open_duty_page,
            open_settings_callback=self.open_settings_section,
            update_check_callback=self.check_for_updates_from_settings
        )

        self.home_page_index = self.stack.addWidget(self.home_page_widget)
        self.dashboard_widgets.append(self.home_page_widget)
        self.page_has_time_buttons[self.home_page_index] = False


    def open_home_page(self):
        if self.home_page_index is not None:
            self.stack.setCurrentIndex(self.home_page_index)
            self.set_time_selector_visible(False)
            self.pause_inactive_web_dashboards()
            self.log_memory_status()

    def open_duty_page(self):
        pages = self.product_dashboard_indexes.get("Дежурство", [])
        if pages:
            self.stack.setCurrentIndex(pages[0]["index"])
            self.pause_inactive_web_dashboards()
            self.log_memory_status()

    def create_duty_mode_page(self):
        self.duty_mode_widget = DutyModeWidget(
            config=self.config,
            profiles=self.profiles,
            credentials=self.credentials,
            graph_card_finder=self.find_graph_card_by_product_section_title,
            source_view_finder=self.find_source_view_by_product_section
        )

        index = self.stack.addWidget(self.duty_mode_widget)
        self.dashboard_widgets.append(self.duty_mode_widget)
        self.page_has_time_buttons[index] = False

        product_name = "Дежурство"
        self.product_dashboard_indexes[product_name] = [{
            "name": "Режим дежурства",
            "index": index,
            "has_time": False,
            "type": "duty_mode",
            "widget": self.duty_mode_widget,
        }]

    @staticmethod
    def _normalize_lookup_text(value):
        return " ".join(str(value or "").split()).casefold()

    def find_dashboard_widget_by_product_section(self, product_name, section_name):
        target_product = self._normalize_lookup_text(product_name)
        target_section = self._normalize_lookup_text(section_name)
        for product, pages in self.product_dashboard_indexes.items():
            if self._normalize_lookup_text(product) != target_product:
                continue
            for page in pages:
                if self._normalize_lookup_text(page.get("name", "")) == target_section:
                    return page.get("widget")
        return None

    def find_graph_card_by_product_section_title(self, product_name, section_name, graph_title):
        widget = self.find_dashboard_widget_by_product_section(product_name, section_name)
        if isinstance(widget, GraphsDashboard):
            return widget.find_graph_card_by_title(graph_title)
        return None

    def find_source_view_by_product_section(self, product_name, section_name):
        widget = self.find_dashboard_widget_by_product_section(product_name, section_name)
        view = getattr(widget, "view", None)
        if view is not None:
            return view
        return None

    def populate_product_combo(self):
        """
        Заполняет список продуктов без Главной.
        Главная открывается кликом по логотипу приложения.
        """
        self.product_combo.blockSignals(True)
        self.product_combo.clear()

        for product_name in self.product_dashboard_indexes.keys():
            if product_name == "Главная":
                continue
            self.product_combo.addItem(product_name, product_name)

        self.product_combo.blockSignals(False)


    def on_product_changed(self, *_args):
        if self.is_updating_selectors:
            return

        product_name = self.product_combo.currentData()
        sections = self.product_dashboard_indexes.get(product_name, [])
        self.logger.info("Выбран продукт: %s", product_name)
        self.logger.info("Найдено разделов для продукта '%s': %s", product_name, len(sections))

        self.is_updating_selectors = True

        self.section_combo.clear()
        for section in sections:
            self.section_combo.addItem(section["name"], section)

        self.is_updating_selectors = False

        if sections:
            self.section_combo.setCurrentIndex(0)
            self.on_section_changed()
            return

        self.logger.info("Для продукта '%s' разделов не найдено.", product_name)
        if self.home_page_index is not None:
            self.open_home_page()

    def on_section_changed(self, *_args):
        if self.is_updating_selectors:
            return

        section = self.section_combo.currentData()
        if not section:
            self.logger.info("Раздел не выбран или отсутствует в section_combo.")
            return

        self.logger.info("Выбран раздел: %s", section.get("name"))
        index = section["index"]
        self.stack.setCurrentIndex(index)
        self.update_toolbar_for_current_page(index)
        self.pause_inactive_web_dashboards()
        self.log_memory_status()


    def on_time_changed(self):
        range_value = self.time_combo.currentData()
        if range_value:
            self.set_time_range(range_value)

    def select_first_dashboard(self):
        """
        При запуске открывается Главная страница.
        """
        if self.home_page_index is not None:
            self.open_home_page()
            self.pause_inactive_web_dashboards()
            return

        if self.product_combo.count() <= 0:
            if self.settings_page_index is not None:
                self.stack.setCurrentIndex(self.settings_page_index)
            return

        self.product_combo.setCurrentIndex(0)
        self.on_product_changed()


    def update_toolbar_for_current_page(self, index):
        has_time = self.page_has_time_buttons.get(index, False)
        self.set_time_selector_visible(has_time)

    def set_time_selector_visible(self, visible):
        self.time_label_action.setVisible(visible)
        self.time_combo_action.setVisible(visible)

    def open_graph_settings(self):
        self.open_settings_section("Продукты и страницы")

    def open_settings_section(self, section_name=None):
        if self.settings_page_index is not None:
            widget = self.stack.widget(self.settings_page_index)
            if section_name and hasattr(widget, "open_section"):
                widget.open_section(section_name)
            self.stack.setCurrentIndex(self.settings_page_index)
            self.set_time_selector_visible(False)
            self.pause_inactive_web_dashboards()

    def check_for_updates_from_settings(self, interactive=False, auto_start_install=False):
        if self.settings_page_index is None:
            return
        widget = self.stack.widget(self.settings_page_index)
        if hasattr(widget, "check_for_updates"):
            widget.check_for_updates(
                interactive=interactive,
                auto_start_install=auto_start_install,
            )

    def pause_inactive_web_dashboards(self):
        current = self.stack.currentWidget()
        for widget in self.dashboard_widgets:
            if widget is current:
                if hasattr(widget, "resume_refresh"):
                    widget.resume_refresh()
            elif isinstance(widget, GraphsDashboard):
                widget.cleanup()
            elif hasattr(widget, "pause_refresh"):
                widget.pause_refresh()

    def count_graph_cards(self):
        total = 0
        for widget in self.dashboard_widgets:
            total += len(getattr(widget, "graph_cards", []) or [])
            total += len(getattr(widget, "cards", []) or [])
        return total

    def active_product_section(self):
        product = self.product_combo.currentData() if hasattr(self, "product_combo") else ""
        section = ""
        current_section = self.section_combo.currentData() if hasattr(self, "section_combo") else None
        if isinstance(current_section, dict):
            section = current_section.get("name", "")
        return product or "", section or ""

    def log_memory_status(self):
        rss_mb = current_rss_mb()
        product, section = self.active_product_section()
        graph_cards = self.count_graph_cards()
        web_views = tracked_web_view_count()
        rss_text = "n/a" if rss_mb is None else f"{rss_mb:.1f}"
        self.logger.info(
            "Memory status: rss_mb=%s graph_cards=%s web_views=%s active_product=%s active_section=%s",
            rss_text,
            graph_cards,
            web_views,
            product,
            section,
        )
        if rss_mb is not None and rss_mb > 3000:
            self.logger.warning("High memory usage detected: rss_mb=%.1f", rss_mb)
            if not self._last_memory_warning:
                self.statusBar().showMessage("Высокое потребление памяти", 10000)
            self._last_memory_warning = True
        elif rss_mb is not None and rss_mb < 2500:
            self._last_memory_warning = False

    def cleanup_web_resources(self):
        self.logger.info("Main window WebEngine cleanup started")
        for widget in list(self.dashboard_widgets):
            if hasattr(widget, "cleanup"):
                widget.cleanup()
        for view, _page in list(self.auth_web_views):
            safe_delete_web_view(view, logger=self.logger, context="auth hidden WebView")
        self.auth_web_views.clear()
        self.logger.info("Main window WebEngine cleanup finished")

    def inject_login(self, view, creds):
        login = creds.get("login", "")
        password = creds.get("password", "")

        if not login or not password:
            return

        safe_login = login.replace("\\", "\\\\").replace("'", "\\'")
        safe_password = password.replace("\\", "\\\\").replace("'", "\\'")

        js = f"""
        (function() {{
            function setValue(selectors, value) {{
                for (const selector of selectors) {{
                    const el = document.querySelector(selector);
                    if (el) {{
                        el.value = value;
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        return true;
                    }}
                }}
                return false;
            }}

            const userSet = setValue([
                'input[name="name"]',
                'input[name="username"]',
                'input#name',
                'input#username',
                'input[type="text"]'
            ], '{safe_login}');

            const passSet = setValue([
                'input[name="password"]',
                'input#password',
                'input[type="password"]'
            ], '{safe_password}');

            if (userSet && passSet) {{
                const button = document.querySelector(
                    'button[type="submit"], input[type="submit"], button[name="enter"], input[name="enter"]'
                );
                if (button) {{
                    button.click();
                }} else {{
                    const form = document.querySelector('form');
                    if (form) form.submit();
                }}
            }}
        }})();
        """

        view.page().runJavaScript(js)

    def closeEvent(self, event):
        if self.duty_mode_widget is not None:
            self.duty_mode_widget.disable_for_shutdown()
        if getattr(self, "metrics_timer", None) is not None:
            self.metrics_timer.stop()
        if getattr(self, "memory_diagnostics_timer", None) is not None:
            self.memory_diagnostics_timer.stop()
        self.cleanup_web_resources()
        super().closeEvent(event)

    def set_time_range(self, range_value):
        self.current_time_range = range_value
        self.config.setdefault("settings", {})["default_time_range"] = range_value
        save_config(self.config)

        current = self.stack.currentWidget()
        if hasattr(current, "set_time_range"):
            current.set_time_range(range_value)

        self.statusBar().showMessage(f"Период графиков: {range_value}")

    def reload_current(self):
        current = self.stack.currentWidget()
        if hasattr(current, "reload_all"):
            current.reload_all()

    def reload_all(self):
        for widget in self.dashboard_widgets:
            if hasattr(widget, "reload_all"):
                widget.reload_all()

        self.statusBar().showMessage("Все разделы обновлены")

    def recreate_shortcut(self):
        script = Path(__file__).resolve().parent.parent / "СОЗДАТЬ_ЯРЛЫК.sh"

        if not script.exists():
            self.statusBar().showMessage("Скрипт СОЗДАТЬ_ЯРЛЫК.sh не найден")
            return

        try:
            subprocess.run(
                ["bash", str(script), "--no-pause"],
                cwd=str(script.parent),
                timeout=20,
                check=False
            )
            self.statusBar().showMessage("Ярлык пересоздан")
        except Exception as error:
            self.statusBar().showMessage(f"Не удалось пересоздать ярлык: {error}")

    def run_uninstaller(self):
        script = Path(__file__).resolve().parent.parent / "УДАЛИТЬ_ДЕЖУРКУ.sh"

        if not script.exists():
            self.statusBar().showMessage("Скрипт УДАЛИТЬ_ДЕЖУРКУ.sh не найден")
            return

        try:
            subprocess.Popen(
                ["bash", str(script)],
                cwd=str(script.parent)
            )
        except Exception as error:
            self.statusBar().showMessage(f"Не удалось запустить удаление: {error}")

    def apply_initial_window_mode(self):
        startup_geometry = self.config.get("_startup_screen_geometry") or {}

        available = None
        if startup_geometry:
            available = QRect(
                int(startup_geometry.get("x", 0)),
                int(startup_geometry.get("y", 0)),
                int(startup_geometry.get("width", 1024)),
                int(startup_geometry.get("height", 768)),
            )
        else:
            screen = QGuiApplication.primaryScreen()
            if screen:
                available = screen.availableGeometry()

        if available is None:
            available = QRect(0, 0, 1024, 768)

        width_percent = float(self.settings.get("window_width_percent", 0.92))
        height_percent = float(self.settings.get("window_height_percent", 0.88))
        desired_width = int(available.width() * width_percent)
        desired_height = int(available.height() * height_percent)
        size, minimum = safe_window_size(
            available,
            desired_width=desired_width,
            desired_height=desired_height,
            margin=40,
            min_width=640,
            min_height=480,
        )
        self.setMinimumSize(minimum)
        rect = QRect(
            available.x() + int((available.width() - size.width()) / 2),
            available.y() + int((available.height() - size.height()) / 2),
            size.width(),
            size.height(),
        )
        rect = clamp_rect_to_available(rect, available, margin=20)
        if not rect_fits_available(rect, available):
            self.logger.warning(
                "Saved/startup window geometry does not fit current availableGeometry; resetting: rect=%s available=%s",
                rect,
                available,
            )
            rect = clamp_rect_to_available(rect, available, margin=20)
        self.setGeometry(rect)
        self.showNormal()

        screen = self.windowHandle().screen() if self.windowHandle() else QGuiApplication.primaryScreen()
        if screen:
            self.logger.info(
                "Main window startup geometry: screen=%s geometry=%s available=%s dpr=%s window=%s",
                screen.name(),
                screen.geometry(),
                screen.availableGeometry(),
                screen.devicePixelRatio(),
                self.geometry(),
            )


    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def exit_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
