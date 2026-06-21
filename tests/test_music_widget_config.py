import unittest

from app.config import collect_exportable_settings
from app.music_config import default_music_widget_config, ensure_music_widget_defaults


class MusicWidgetConfigTests(unittest.TestCase):
    def test_defaults_added_to_old_config(self):
        config = {"settings": {"theme": "mass_effect"}}
        music = ensure_music_widget_defaults(config)
        self.assertIn("music_widget", config)
        self.assertEqual(music["active_provider"], "yandex_music")
        self.assertTrue(music["collapsed"])
        self.assertTrue(music["mini_player_enabled"])
        self.assertEqual(music["panel_open"], False)
        ids = {p["id"] for p in music["providers"]}
        self.assertIn("yandex_music", ids)
        self.assertIn("spotify", ids)
        self.assertIn("custom", ids)
        self.assertIn(music["visualizer_mode"], {"auto", "real", "decorative"})

    def test_visualizer_values_normalized(self):
        config = {"music_widget": {"visualizer_bar_count": 1, "visualizer_fps": 500, "visualizer_mode": "bad"}}
        music = ensure_music_widget_defaults(config)
        self.assertEqual(music["visualizer_bar_count"], 4)
        self.assertEqual(music["visualizer_fps"], 60)
        self.assertEqual(music["visualizer_mode"], "auto")

    def test_mini_player_and_drawer_values_normalized(self):
        config = {"music_widget": {"mini_player_width": 10, "mini_player_height": 10, "panel_width": 10, "metadata_poll_ms": 10, "visualizer_compact_bar_count": 2}}
        music = ensure_music_widget_defaults(config)
        self.assertEqual(music["mini_player_width"], 320)
        self.assertEqual(music["mini_player_height"], 42)
        self.assertEqual(music["panel_width"], 320)
        self.assertEqual(music["metadata_poll_ms"], 500)
        self.assertEqual(music["visualizer_compact_bar_count"], 4)

    def test_music_widget_safe_export_has_no_sensitive_keys(self):
        config = {"music_widget": default_music_widget_config()}
        exported = collect_exportable_settings(config)
        self.assertIn("music_widget", exported)
        text = str(exported).lower()
        for forbidden in ("password", "token", "cookie", "secret"):
            self.assertNotIn(forbidden, text)
        self.assertIn("profile_dir", exported["music_widget"]["providers"][0])
        self.assertIn("url", exported["music_widget"]["providers"][0])


if __name__ == "__main__":
    unittest.main()
