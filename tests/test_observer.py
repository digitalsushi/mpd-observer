import unittest
from types import SimpleNamespace
from unittest.mock import patch

from mpd_observer.observer import Observer


class ObserverTests(unittest.TestCase):
    def test_multiple_snapshot_cycles_share_one_mpd_connection(self):
        mpd = SimpleNamespace(
            stream_metadata_poll_seconds=0,
            reconnect_max_seconds=30,
        )
        observer = Observer(
            mpd,
            SimpleNamespace(enabled=False),
            SimpleNamespace(enabled=False),
        )
        snapshot = {
            "connected": True, "track": None, "duration": None,
            "elapsed": None, "observed_at": 0,
        }
        connection = SimpleNamespace()
        context = patch("mpd_observer.observer.MpdConnection")
        with context as mpd_connection, patch(
            "mpd_observer.observer.read_snapshot_from_connection",
            side_effect=[snapshot, snapshot],
        ) as read:
            mpd_connection.return_value.__enter__.return_value = connection
            original_wait = observer._stop.wait
            waits = 0

            def stop_after_two_reads(_seconds):
                nonlocal waits
                waits += 1
                if waits == 2:
                    observer._stop.set()
                return original_wait(0)

            with patch.object(observer._stop, "wait", side_effect=stop_after_two_reads):
                observer._run()

        mpd_connection.assert_called_once_with(mpd)
        self.assertEqual(read.call_count, 2)
        self.assertIs(read.call_args_list[0].args[0], connection)
        self.assertIs(read.call_args_list[1].args[0], connection)

    def test_raudio_status_is_requested_once_per_raw_stream_title(self):
        observer = Observer(
            SimpleNamespace(),
            SimpleNamespace(enabled=True),
            SimpleNamespace(),
        )
        response = {
            "uri": "music/file.flac",
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
        response = {"uri": "music/file.flac", "title": "", "artist": "",
                    "album": "", "artwork": ""}
        with patch("mpd_observer.observer.read_raudio_status", return_value=response) as read:
            observer._enrich({"track": {"uri": response["uri"], "title": "First"}})
            observer._enrich({"track": {"uri": response["uri"], "title": "Second"}})
        self.assertEqual(read.call_count, 2)

    def test_raudio_status_is_not_requested_for_http_streams(self):
        observer = Observer(
            SimpleNamespace(),
            SimpleNamespace(enabled=True),
            SimpleNamespace(),
        )
        snapshot = {"track": {
            "uri": "http://radio.example/stream",
            "artist": "Artist",
            "title": "Track",
        }}
        with patch("mpd_observer.observer.read_raudio_status") as read:
            observer._enrich(snapshot)
        read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
