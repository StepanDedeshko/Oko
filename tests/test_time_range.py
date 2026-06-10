import unittest
from urllib.parse import parse_qs, urlparse

from app.time_range import add_graph_cache_buster, apply_time_range_to_url


class TimeRangeTests(unittest.TestCase):
    def test_graph_cache_buster_replaces_existing_value(self):
        url = "https://zabbix.example/chart2.php?graphid=1&_oko_graph_refresh_ts=old&period=3600"

        refreshed = add_graph_cache_buster(url, timestamp_ms=12345)

        query = parse_qs(urlparse(refreshed).query)
        self.assertEqual(query["_oko_graph_refresh_ts"], ["12345"])
        self.assertEqual(query["period"], ["3600"])
        self.assertEqual(query["graphid"], ["1"])

    def test_time_range_then_cache_buster_preserves_selected_period(self):
        ranged = apply_time_range_to_url("https://zabbix.example/chart2.php?graphid=1&period=3600", "3h")
        refreshed = add_graph_cache_buster(ranged, timestamp_ms=777)

        query = parse_qs(urlparse(refreshed).query)
        self.assertEqual(query["period"], ["10800"])
        self.assertEqual(query["_oko_graph_refresh_ts"], ["777"])


if __name__ == "__main__":
    unittest.main()
