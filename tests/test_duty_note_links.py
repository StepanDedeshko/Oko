import unittest

from app.note_links import plain_text_to_safe_html_with_links


class DutyNoteLinkHtmlTests(unittest.TestCase):
    def test_plain_text_without_links(self):
        self.assertEqual(plain_text_to_safe_html_with_links("hello\nworld"), "hello<br>world")

    def test_https_link(self):
        html = plain_text_to_safe_html_with_links("See https://example.com/path")
        self.assertIn('<a href="https://example.com/path">https://example.com/path</a>', html)

    def test_http_link(self):
        html = plain_text_to_safe_html_with_links("See http://example.com")
        self.assertIn('<a href="http://example.com">http://example.com</a>', html)

    def test_html_characters_are_escaped(self):
        html = plain_text_to_safe_html_with_links('<script>alert(1)</script> https://safe.local/?a=1&b=2')
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', html)
        self.assertIn('https://safe.local/?a=1&amp;b=2', html)
        self.assertNotIn('<script>', html)

    def test_multiple_links(self):
        html = plain_text_to_safe_html_with_links('http://one.local and https://two.local.')
        self.assertEqual(html.count('<a href='), 2)
        self.assertTrue(html.endswith('</a>.'))


if __name__ == '__main__':
    unittest.main()
