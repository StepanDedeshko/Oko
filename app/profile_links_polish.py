from __future__ import annotations


def install_profile_links_polish() -> bool:
    """Keep Profile limited to credentials, never shared technical URLs."""
    import app.home_config as home_config

    cls = home_config.ProfileWidget
    if getattr(cls, "_profile_links_polished", False):
        return False

    original_init = cls.__init__
    original_save = cls.save

    def __init__(self, config, logout_callback=None, parent=None):
        original_init(self, config, logout_callback=logout_callback, parent=parent)

        # The URL is edited only on Settings -> Links.  Keep the legacy field
        # object hidden because Profile.save() from older builds still expects it.
        field = getattr(self, "redmine_login_url_input", None)
        if field is not None:
            field.hide()

        for label in self.findChildren(home_config.QLabel):
            text = str(label.text() or "")
            if "Login URL" in text and "Ссылки" in text:
                label.hide()

    def save(self):
        # A Profile page can remain open while the URL is changed on Links.
        # Refresh its hidden compatibility field before invoking the old save
        # handler so stale profile state can never overwrite the central value.
        live = home_config.ensure_live_monitor_defaults(self.config)
        current_url = str(
            live.get("redmine_login_url") or home_config.DEFAULT_REDMINE_LOGIN_URL
        ).strip()
        field = getattr(self, "redmine_login_url_input", None)
        if field is not None:
            field.setText(current_url)
        return original_save(self)

    cls.__init__ = __init__
    cls.save = save
    cls._profile_links_polished = True
    return True
