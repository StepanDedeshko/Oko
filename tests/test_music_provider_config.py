import unittest
from pathlib import Path

from app.music_config import ensure_music_widget_defaults, find_provider, first_enabled_provider, provider_paths


class MusicProviderConfigTests(unittest.TestCase):
    def test_active_provider_found(self):
        settings = ensure_music_widget_defaults({})
        self.assertEqual(find_provider(settings, "spotify")["name"], "Spotify")

    def test_missing_active_provider_falls_back_to_first_enabled(self):
        settings = ensure_music_widget_defaults({"music_widget": {"active_provider": "missing"}})
        self.assertEqual(first_enabled_provider(settings)["id"], "yandex_music")
        self.assertEqual(settings["active_provider"], "yandex_music")

    def test_custom_empty_url_is_allowed(self):
        settings = ensure_music_widget_defaults({})
        custom = next(p for p in settings["providers"] if p["id"] == "custom")
        self.assertEqual(custom["url"], "")

    def test_provider_profile_paths_are_distinct(self):
        settings = ensure_music_widget_defaults({})
        paths = [provider_paths(p, Path("/tmp/oko"))[0] for p in settings["providers"]]
        self.assertEqual(len(paths), len(set(paths)))

    def test_disabled_provider_not_selected_automatically(self):
        config = {"music_widget": {"providers": [{"id": "a", "enabled": False}, {"id": "b", "enabled": True}]}}
        settings = ensure_music_widget_defaults(config)
        self.assertEqual(first_enabled_provider(settings)["id"], "b")


if __name__ == "__main__":
    unittest.main()
