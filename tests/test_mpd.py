import io
import unittest
from unittest.mock import patch

from mpd_observer.mpd import MpdConnection, MpdError, read_artwork, read_snapshot
from mpd_observer.settings import MpdSettings


class FakeConnection:
    version = "0.23.12"

    def __init__(self, _settings): pass
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def command(self, name, *args):
        if name == "status":
            return [b"state: play", b"elapsed: 12.5", b"duration: 200"]
        return [b"file: music/test.flac", b"Artist: Artist", b"Title: Title", b"Album: Album"]


class FakeStreamConnection(FakeConnection):
    def command(self, name, *args):
        if name == "status":
            return [b"state: play"]
        return [
            b"file: http://radio.example/stream",
            b"Title: Jesper Kyd - Lunar Surface (Extended Mix)",
        ]


class MpdTests(unittest.TestCase):
    def test_normalizes_snapshot(self):
        settings = MpdSettings("127.0.0.1", 6600, 1, 2)
        with patch("mpd_observer.mpd.MpdConnection", FakeConnection):
            result = read_snapshot(settings)
        self.assertTrue(result["connected"])
        self.assertEqual(result["state"], "play")
        self.assertEqual(result["track"]["title"], "Title")
        self.assertEqual(result["track"]["artist"], "Artist")
        self.assertEqual(result["elapsed"], 12.5)

    def test_rejects_commands_outside_allowlist(self):
        client = object.__new__(MpdConnection)
        client.stream = io.BytesIO()
        with self.assertRaises(MpdError):
            client.command("play")

    def test_splits_conventional_icecast_artist_and_title(self):
        settings = MpdSettings("127.0.0.1", 6600, 1, 2)
        with patch("mpd_observer.mpd.MpdConnection", FakeStreamConnection):
            track = read_snapshot(settings)["track"]
        self.assertEqual(track["artist"], "Jesper Kyd")
        self.assertEqual(track["title"], "Lunar Surface (Extended Mix)")

    def test_does_not_open_mpd_artwork_connection_for_http_stream(self):
        settings = MpdSettings("127.0.0.1", 6600, 1, 2)
        with patch("mpd_observer.mpd.MpdConnection") as connection:
            self.assertIsNone(read_artwork(settings, "http://radio.example/stream"))
        connection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
