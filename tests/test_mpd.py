import io
import unittest
from unittest.mock import patch

from mpd_observer.mpd import MpdConnection, MpdError, read_snapshot
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


if __name__ == "__main__":
    unittest.main()
