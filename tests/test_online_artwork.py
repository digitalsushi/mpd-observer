import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from mpd_observer.online_artwork import (
    _METADATA_ONLY, _matching_recording, _read_cache, _release_title,
    _trusted_image_url,
)


class OnlineArtworkTests(unittest.TestCase):
    def setUp(self):
        self.data = {"recordings": [{
            "score": 100,
            "title": "Marcus Tells a Story",
            "artist-credit": [{"name": "Finishing Move Inc."}],
            "releases": [{"status": "Official", "release-group": {
                "id": "group-id", "title": "Borderlands 3 (Original Soundtrack)"
            }}],
        }]}

    def test_accepts_high_confidence_exact_match(self):
        match = _matching_recording(
            self.data, "Finishing Move Inc.", "Marcus Tells a Story", 95
        )
        self.assertIsNotNone(match)

    def test_rejects_wrong_artist_despite_search_score(self):
        match = _matching_recording(self.data, "Another Artist", "Marcus Tells a Story", 95)
        self.assertIsNone(match)

    def test_only_trusts_cover_archive_hosts(self):
        self.assertTrue(_trusted_image_url("https://ia800.example.archive.org/image.jpg"))
        self.assertFalse(_trusted_image_url("https://example.com/image.jpg"))

    def test_extracts_album_from_official_release_group(self):
        self.assertEqual(
            _release_title(self.data["recordings"][0]),
            "Borderlands 3 (Original Soundtrack)",
        )

    def test_matched_metadata_without_artwork_is_permanent_when_ttl_is_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            metadata = Path(directory) / "track.json"
            metadata.write_text(json.dumps({
                "cached_at": time.time() - 10 * 365 * 86400,
                "found": False,
                "matched": True,
                "duration_seconds": 180,
                "album": "An Album",
            }))
            settings = SimpleNamespace(
                positive_ttl_seconds=0, negative_ttl_seconds=21600, max_bytes=1000,
            )
            self.assertIs(
                _read_cache(settings, Path(directory) / "track.image", metadata),
                _METADATA_ONLY,
            )

    def test_unidentified_track_still_expires_on_negative_ttl(self):
        with tempfile.TemporaryDirectory() as directory:
            metadata = Path(directory) / "track.json"
            metadata.write_text(json.dumps({
                "cached_at": time.time() - 21601,
                "found": False,
                "matched": False,
                "duration_seconds": None,
                "album": None,
            }))
            settings = SimpleNamespace(
                positive_ttl_seconds=0, negative_ttl_seconds=21600, max_bytes=1000,
            )
            self.assertIs(_read_cache(settings, Path(directory) / "track.image", metadata), False)


if __name__ == "__main__":
    unittest.main()
