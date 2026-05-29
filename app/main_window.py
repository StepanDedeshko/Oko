from datetime import datetime
import subprocess
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, QUrl
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

        self.is_updating_selectors = False
        self.metrics_provider = SystemMetricsProvider()
        self.loading_screen = None
        self.problem_counter_ready = False
        self.current_problem_loading_widget = None
        self.problem_loading_active = False
        self.logger = get_logger()

        self.setWindowTitle(APP_NAME)

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

        self.update_bottom_hud()

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
        self.product_combo.setMinimumWidth(180)
        self.product_combo.currentIndexChanged.connect(self.on_product_changed)
        self.product_combo.activated.connect(self.on_product_changed)

        self.section_combo = QComboBox()
        self.section_combo.setMinimumWidth(180)
        self.section_combo.currentIndexChanged.connect(self.on_section_changed)
        self.section_combo.activated.connect(self.on_section_changed)

        self.time_combo = QComboBox()
        self.time_combo.setMinimumWidth(130)
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

        self.settings_button = QPushButton("Настройки")
        self.settings_button.setToolTip("Открыть настройки приложения")
        self.settings_button.clicked.connect(self.open_graph_settings)

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
        self.toolbar.addWidget(self.settings_button)
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

            view = QWebEngineView()
            page = QWebEnginePage(profile, view)
            view.setPage(page)
            view.loadFinished.connect(lambda ok, v=view, c=creds: self.inject_login(v, c))
            view.load(QUrl(login_url))

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
                        credentials=self.credentials.get(zabbix_id, {})
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
            open_duty_callback=self.open_duty_page
        )

        self.home_page_index = self.stack.addWidget(self.home_page_widget)
        self.dashboard_widgets.append(self.home_page_widget)
        self.page_has_time_buttons[self.home_page_index] = False


    def open_home_page(self):
        if self.home_page_index is not None:
            self.stack.setCurrentIndex(self.home_page_index)
            self.set_time_selector_visible(False)

    def open_duty_page(self):
        pages = self.product_dashboard_indexes.get("Дежурство", [])
        if pages:
            self.stack.setCurrentIndex(pages[0]["index"])

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
        if self.settings_page_index is not None:
            self.stack.setCurrentIndex(self.settings_page_index)
            self.set_time_selector_visible(False)

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
        mode = self.settings.get("window_mode", "maximized")

        startup_geometry = self.config.get("_startup_screen_geometry") or {}

        if startup_geometry:
            class _RectLike:
                def __init__(self, data):
                    self._data = data

                def x(self): return int(self._data.get("x", 0))
                def y(self): return int(self._data.get("y", 0))
                def width(self): return int(self._data.get("width", 1500))
                def height(self): return int(self._data.get("height", 900))

            available = _RectLike(startup_geometry)
            width = int(available.width() * float(self.settings.get("window_width_percent", 0.98)))
            height = int(available.height() * float(self.settings.get("window_height_percent", 0.95)))
            self.resize(width, height)
            self.move(
                available.x() + int((available.width() - width) / 2),
                available.y() + int((available.height() - height) / 2)
            )
        else:
            screen = QGuiApplication.primaryScreen()
            if screen:
                available = screen.availableGeometry()
                width = int(available.width() * float(self.settings.get("window_width_percent", 0.98)))
                height = int(available.height() * float(self.settings.get("window_height_percent", 0.95)))
                self.resize(width, height)
                self.move(
                    available.x() + int((available.width() - width) / 2),
                    available.y() + int((available.height() - height) / 2)
                )
            else:
                self.resize(1500, 900)

        if mode == "fullscreen":
            self.showFullScreen()
        elif mode == "maximized":
            self.showMaximized()
        else:
            self.showNormal()


    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showMaximized()
        else:
            self.showFullScreen()

    def exit_fullscreen(self):
        if self.isFullScreen():
            self.showMaximized()
