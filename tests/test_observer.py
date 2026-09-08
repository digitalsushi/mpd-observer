import unittest
from types import SimpleNamespace
from unittest.mock import patch

from mpd_observer.observer import Observer


class ObserverTests(unittest.TestCase):
    def test_raudio_status_is_requested_once_per_raw_stream_title(self):
        observer = Observer(
            SimpleNamespace(),
            SimpleNamespace(enabled=True),
            SimpleNamespace(),
        )
        response = {
            "uri": "http://radio/stream",
            "title": "Track",
            "artist": "Artist",
            "album": "Album",
            "artwork": "/cover.jpg",
        }
        first = {"track": {"uri": response["uri"], "title": "Artist - Track"}}
        second = {"track": {"uri": response["uri"], "title": "Artist - Track"}}
        with patch("mpd_observer.observer.read_raudio_status", return_value=response) as read:
            observer._enrich(first)
            observer._enrich(second)
        read.assert_called_once()
        self.assertEqual(first["track"]["artist"], "Artist")
        self.assertEqual(second["track"]["album"], "Album")
        self.assertEqual(second["raudio_artwork"], "/cover.jpg")

    def test_raudio_status_is_requested_again_for_a_new_raw_title(self):
        observer = Observer(
            SimpleNamespace(),
            SimpleNamespace(enabled=True),
            SimpleNamespace(),
        )
        response = {"uri": "http://radio/stream", "title": "", "artist": "",
                    "album": "", "artwork": ""}
        with patch("mpd_observer.observer.read_raudio_status", return_value=response) as read:
            observer._enrich({"track": {"uri": response["uri"], "title": "First"}})
            observer._enrich({"track": {"uri": response["uri"], "title": "Second"}})
        self.assertEqual(read.call_count, 2)


if __name__ == "__main__":
    unittest.main()
