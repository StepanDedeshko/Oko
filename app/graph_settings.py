from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.config import save_config
from app.safe_widgets import NoWheelComboBox


class GraphSettingsWidget(QWidget):
    """
    Настройки графиков.
    """

    def __init__(self, config, on_saved_callback=None):
        super().__init__()

        self.config = config
        self.on_saved_callback = on_saved_callback
        self.rows = []

        root = QVBoxLayout(self)

        title = QLabel("Настройки графиков")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        hint = QLabel(
            "Для каждого графика можно указать отдельную ссылку для отображения "
            "и отдельную ссылку для кнопки «Открыть в Zabbix». "
            "Если URL кнопки пустой — кнопка открывает URL графика."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        selector_layout = QHBoxLayout()

        self.product_combo = NoWheelComboBox()
        self.dashboard_combo = NoWheelComboBox()

        self.product_combo.currentIndexChanged.connect(self.reload_dashboards_combo)
        self.dashboard_combo.currentIndexChanged.connect(self.load_graphs)

        selector_layout.addWidget(QLabel("Продукт:"))
        selector_layout.addWidget(self.product_combo)
        selector_layout.addWidget(QLabel("Раздел:"))
        selector_layout.addWidget(self.dashboard_combo)
        selector_layout.addStretch()

        root.addLayout(selector_layout)

        buttons = QHBoxLayout()

        add_button = QPushButton("Добавить график")
        add_button.clicked.connect(self.add_graph)

        save_button = QPushButton("Сохранить")
        save_button.clicked.connect(self.save)

        buttons.addWidget(add_button)
        buttons.addWidget(save_button)
        buttons.addStretch()

        root.addLayout(buttons)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        root.addWidget(scroll, stretch=1)

        self.container = QWidget()
        self.graphs_layout = QVBoxLayout(self.container)
        scroll.setWidget(self.container)

        self.load_products()

    def load_products(self):
        self.product_combo.blockSignals(True)
        self.product_combo.clear()

        for index, product in enumerate(self.config.get("products", [])):
            if product.get("enabled", True):
                self.product_combo.addItem(product.get("name", f"Продукт {index + 1}"), index)

        self.product_combo.blockSignals(False)
        self.reload_dashboards_combo()

    def get_selected_product(self):
        index = self.product_combo.currentData()
        products = self.config.get("products", [])

        if index is None or index < 0 or index >= len(products):
            return None

        return products[index]

    def get_selected_dashboard(self):
        product = self.get_selected_product()
        index = self.dashboard_combo.currentData()

        if product is None or index is None:
            return None

        dashboards = product.get("dashboards", [])
        if index < 0 or index >= len(dashboards):
            return None

        return dashboards[index]

    def reload_dashboards_combo(self):
        self.dashboard_combo.blockSignals(True)
        self.dashboard_combo.clear()

        product = self.get_selected_product()
        if product:
            for index, dashboard in enumerate(product.get("dashboards", [])):
                if dashboard.get("enabled", True) and dashboard.get("type") == "graphs_grid":
                    self.dashboard_combo.addItem(dashboard.get("name", f"Графики {index + 1}"), index)

        self.dashboard_combo.blockSignals(False)
        self.load_graphs()

    def clear_graphs(self):
        self.rows = []

        while self.graphs_layout.count():
            item = self.graphs_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def load_graphs(self):
        self.clear_graphs()

        dashboard = self.get_selected_dashboard()
        if dashboard is None:
            self.graphs_layout.addWidget(QLabel("Нет разделов с графиками."))
            return

        graphs = dashboard.setdefault("graphs", [])

        for index, graph in enumerate(graphs):
            self.add_graph_widget(index, graph)

        self.graphs_layout.addStretch(1)

    def add_graph_widget(self, index, graph):
        group = QGroupBox(f"График {index + 1}")
        form = QFormLayout(group)

        enabled = QCheckBox("Включён")
        enabled.setChecked(graph.get("enabled", True))

        title = QLineEdit()
        title.setText(graph.get("title", ""))
        title.setPlaceholderText("Название графика")

        url = QLineEdit()
        url.setText(graph.get("url", ""))
        url.setPlaceholderText("URL графика, который отображается в карточке")

        open_url = QLineEdit()
        open_url.setText(
            graph.get("open_url")
            or graph.get("zabbix_url")
            or graph.get("external_url")
            or ""
        )
        open_url.setPlaceholderText("URL для кнопки «Открыть в Zabbix». Можно оставить пустым.")

        use_time_range = QCheckBox("Применять период к URL графика")
        use_time_range.setChecked(graph.get("use_time_range", True))

        delete_button = QPushButton("Удалить этот график")
        delete_button.clicked.connect(lambda checked=False, g=group: self.delete_graph_widget(g))

        form.addRow("", enabled)
        form.addRow("Название:", title)
        form.addRow("URL графика:", url)
        form.addRow("URL кнопки «Открыть в Zabbix»:", open_url)
        form.addRow("", use_time_range)
        form.addRow("", delete_button)

        self.rows.append({
            "group": group,
            "enabled": enabled,
            "title": title,
            "url": url,
            "open_url": open_url,
            "use_time_range": use_time_range,
        })

        self.graphs_layout.addWidget(group)

    def add_graph(self):
        self.add_graph_widget(len(self.rows), {
            "enabled": True,
            "title": "Новый график",
            "url": "",
            "open_url": "",
            "use_time_range": True,
        })

    def delete_graph_widget(self, group):
        self.rows = [row for row in self.rows if row["group"] is not group]
        group.deleteLater()

    def save(self):
        dashboard = self.get_selected_dashboard()
        if dashboard is None:
            QMessageBox.warning(self, "Ошибка", "Не выбран раздел с графиками.")
            return

        graphs = []

        for row in self.rows:
            title = row["title"].text().strip()
            url = row["url"].text().strip()
            open_url = row["open_url"].text().strip()

            if not title and not url and not open_url:
                continue

            if not title:
                QMessageBox.warning(self, "Ошибка", "У одного из графиков не указано название.")
                return

            if not url:
                QMessageBox.warning(self, "Ошибка", f"У графика «{title}» не указан URL графика.")
                return

            graph = {
                "enabled": row["enabled"].isChecked(),
                "title": title,
                "url": url,
                "use_time_range": row["use_time_range"].isChecked(),
            }

            if open_url:
                graph["open_url"] = open_url

            graphs.append(graph)

        dashboard["graphs"] = graphs
        save_config(self.config)

        QMessageBox.information(
            self,
            "Сохранено",
            "Настройки графиков сохранены. После изменения ссылок лучше перезапустить Дежурку."
        )

        if self.on_saved_callback:
            self.on_saved_callback()
