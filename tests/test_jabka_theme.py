import unittest

from app.jabka_theme import (
    JABKA_APP_NAME,
    JABKA_THEME_NAME,
    install_jabka_theme,
    is_jabka_theme,
    jabka_display_name,
    jabka_sound_path,
    themed_text,
    theme_asset_path,
)
from app.theme import get_available_themes


class JabkaThemeFoundationTests(unittest.TestCase):
    def setUp(self):
        install_jabka_theme()

    def test_jabka_theme_is_available(self):
        themes = dict(get_available_themes())
        self.assertIn(JABKA_THEME_NAME, themes)
        self.assertEqual(themes[JABKA_THEME_NAME], "Жабка")

    def test_jabka_display_name(self):
        self.assertEqual(jabka_display_name(JABKA_THEME_NAME), JABKA_APP_NAME)
        self.assertEqual(jabka_display_name("mass_effect", default="Око"), "Око")

    def test_jabka_text_overrides_only_apply_to_jabka(self):
        self.assertTrue(is_jabka_theme("jabka"))
        self.assertEqual(themed_text("jabka", "Главная страница"), "Мое болото")
        self.assertEqual(themed_text("jabka", "Перейти в режим дежурства"), "Дежурный жаб")
        self.assertEqual(themed_text("jabka", "Администрирование"), "Жабий админ")
        self.assertEqual(themed_text("jabka", "Режим разработчика"), "Режим картофельной жабки")
        self.assertEqual(themed_text("jabka", "Обновление"), "Улучшения болота")
        self.assertEqual(themed_text("jabka", "Выход"), "Покинуть болото")
        self.assertEqual(themed_text("mass_effect", "Главная страница"), "Главная страница")
        self.assertEqual(themed_text("dark_1", "Выход"), "Выход")

    def test_jabka_asset_paths_are_centralized(self):
        self.assertTrue(str(theme_asset_path("frogs", "frog_main.svg")).endswith("assets/themes/jabka/frogs/frog_main.svg"))
        self.assertTrue(str(jabka_sound_path("jabbix_graph_check_kvak.wav")).endswith("assets/themes/jabka/sounds/jabbix_graph_check_kvak.wav"))

    def test_jabka_svg_assets_exist(self):
        required_assets = [
            theme_asset_path("backgrounds", "swamp_main.svg"),
            theme_asset_path("backgrounds", "swamp_duty.svg"),
            theme_asset_path("backgrounds", "swamp_settings.svg"),
            theme_asset_path("backgrounds", "swamp_profile.svg"),
            theme_asset_path("backgrounds", "swamp_live_zabbix.svg"),
            theme_asset_path("frogs", "frog_main.svg"),
            theme_asset_path("frogs", "frog_duty.svg"),
            theme_asset_path("frogs", "frog_settings.svg"),
            theme_asset_path("frogs", "frog_profile.svg"),
            theme_asset_path("frogs", "frog_live_zabbix.svg"),
            theme_asset_path("frogs", "frog_developer.svg"),
        ]
        for path in required_assets:
            self.assertTrue(path.exists(), f"Missing Jabbix asset: {path}")


if __name__ == "__main__":
    unittest.main()
