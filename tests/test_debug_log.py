import unittest

from mpd_observer.debug_log import ConsoleLog


class DebugLogTests(unittest.TestCase):
    def test_keeps_only_the_configured_tail_and_escapes_html(self):
        console = ConsoleLog(2)
        console.append("discarded")
        console.append("<track>")
        console.append("artist & title")
        page = console.page().decode("utf-8")
        self.assertNotIn("discarded", page)
        self.assertIn("&lt;track&gt;", page)
        self.assertIn("artist &amp; title", page)

    def test_coalesces_consecutive_repeated_lines_when_the_message_changes(self):
        console = ConsoleLog(10)
        self.assertEqual(console.append("GET /api/now-playing"), ["GET /api/now-playing"])
        self.assertEqual(console.append("GET /api/now-playing"), [])
        self.assertEqual(console.append("GET /api/now-playing"), [])
        self.assertNotIn("repeated", console.page().decode("utf-8"))
        self.assertEqual(console.append("Artwork MusicBrainz: searching"), [
            "Last message repeated 2 times", "Artwork MusicBrainz: searching",
        ])
        page = console.page().decode("utf-8")
        self.assertEqual(page.count("GET /api/now-playing"), 1)
        self.assertIn("Last message repeated 2 times", page)
        self.assertLess(page.index("Last message repeated"), page.index("Artwork MusicBrainz"))


if __name__ == "__main__":
    unittest.main()
