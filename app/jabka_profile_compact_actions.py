from __future__ import annotations

from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.jabka_theme import is_jabka_config


JABKA_PROFILE_COMPACT_QSS = r"""
QPushButton#ProfileLogoutButton {
    background: #8D1D1D;
    color: #FFF7F3;
    border: 1px solid #FF6B5E;
    border-radius: 11px;
    padding: 8px 16px;
    font-weight: 800;
}
QPushButton#ProfileLogoutButton:hover {
    background: #B62A24;
    border-color: #FF9A8F;
}
QPushButton#ProfileLogoutButton:pressed {
    background: #681313;
}
QWidget#ProfileServiceGroupsColumn {
    background: transparent;
}
"""


def _find_layout_with_widget(root, target):
    for index in range(root.count()):
        item = root.itemAt(index)
        layout = item.layout()
        if layout is None:
            continue
        for child_index in range(layout.count()):
            child = layout.itemAt(child_index).widget()
            if child is target:
                return layout
    return None


def apply_jabka_profile_compact_actions(widget) -> bool:
    if widget is None or not is_jabka_config(getattr(widget, "config", None)):
        return False
    if widget.property("jabka_profile_compact_actions"):
        return False

    columns = getattr(widget, "profile_columns", None)
    service_card = getattr(widget, "profile_service_groups_card", None)
    save_button = getattr(widget, "profile_save_button", None)
    logout_button = getattr(widget, "logout_button", None)
    root = widget.layout()

    if (
        not isinstance(columns, QSplitter)
        or not isinstance(service_card, QGroupBox)
        or root is None
        or save_button is None
        or logout_button is None
    ):
        return False

    # The service-group editor should be a compact card at the top-right,
    # not a box stretched to the full profile height.
    service_card.setMinimumHeight(250)
    service_card.setMaximumHeight(330)
    service_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

    group_list = getattr(widget, "profile_service_groups_list", None)
    group_stack = getattr(widget, "profile_service_group_stack", None)
    if group_list is not None:
        group_list.setMinimumHeight(170)
        group_list.setMaximumHeight(230)
    if group_stack is not None:
        group_stack.setMinimumHeight(170)
        group_stack.setMaximumHeight(230)

    service_column = QWidget(columns)
    service_column.setObjectName("ProfileServiceGroupsColumn")
    service_column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    service_layout = QVBoxLayout(service_column)
    service_layout.setContentsMargins(0, 0, 0, 0)
    service_layout.setSpacing(0)

    old_service_card = columns.replaceWidget(1, service_column)
    if old_service_card is not service_card:
        return False
    service_layout.addWidget(service_card, stretch=0)
    service_layout.addStretch(1)

    # Remove the large top account box. The original logout button and callback
    # are preserved, but the action moves to the bottom action row.
    account_box = None
    for box in widget.findChildren(QGroupBox):
        if box.title().strip() == "Аккаунт Око":
            account_box = box
            break
    if account_box is not None:
        root.removeWidget(account_box)
        account_box.hide()

    logout_button.setParent(widget)
    logout_button.setObjectName("ProfileLogoutButton")
    logout_button.setMinimumWidth(210)
    logout_button.show()

    actions = _find_layout_with_widget(root, save_button)
    if not isinstance(actions, QHBoxLayout):
        return False
    actions.addWidget(logout_button)

    widget.profile_service_groups_column = service_column
    widget.profile_account_box = account_box
    widget.profile_logout_button = logout_button
    widget.setStyleSheet(widget.styleSheet() + "\n" + JABKA_PROFILE_COMPACT_QSS)
    widget.setProperty("jabka_profile_compact_actions", True)
    return True


def install_jabka_profile_compact_actions() -> bool:
    import app.home_config as home_config

    cls = home_config.ProfileWidget
    if getattr(cls, "_jabka_profile_compact_actions_installed", False):
        return False

    original_init = cls.__init__

    def __init__(self, config, logout_callback=None, parent=None):
        original_init(self, config, logout_callback, parent)
        apply_jabka_profile_compact_actions(self)

    cls.__init__ = __init__
    cls._jabka_profile_compact_actions_installed = True
    return True
