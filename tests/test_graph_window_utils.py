import unittest

from PySide6.QtCore import QRect

from app.graph_window_utils import calculate_graph_window_geometry


class GraphWindowGeometryTests(unittest.TestCase):
    def test_large_screen_uses_preferred_size_and_centers(self):
        geometry = calculate_graph_window_geometry(QRect(0, 0, 1920, 1080))
        self.assertEqual(geometry.width(), 1200)
        self.assertEqual(geometry.height(), 800)
        self.assertGreaterEqual(geometry.x(), 0)
        self.assertGreaterEqual(geometry.y(), 0)
        self.assertLessEqual(geometry.right(), 1919)
        self.assertLessEqual(geometry.bottom(), 1079)

    def test_small_screen_clamps_to_90_percent(self):
        available = QRect(10, 20, 1000, 700)
        geometry = calculate_graph_window_geometry(available)
        self.assertLessEqual(geometry.width(), 900)
        self.assertLessEqual(geometry.height(), 630)
        self.assertGreaterEqual(geometry.left(), available.left())
        self.assertGreaterEqual(geometry.top(), available.top())
        self.assertLessEqual(geometry.right(), available.right())
        self.assertLessEqual(geometry.bottom(), available.bottom())
