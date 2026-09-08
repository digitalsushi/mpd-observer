import unittest

from mpd_observer.raudio import _same_origin_url


class RAudioTests(unittest.TestCase):
    def test_accepts_relative_artwork_on_configured_origin(self):
        result = _same_origin_url("http://192.0.2.10", "/data/shm/online.jpg")
        self.assertEqual(result, "http://192.0.2.10/data/shm/online.jpg")

    def test_rejects_external_artwork_origin(self):
        result = _same_origin_url("http://192.0.2.10", "https://example.com/cover.jpg")
        self.assertIsNone(result)

    def test_accepts_raudio_encoded_filesystem_path(self):
        result = _same_origin_url("http://192.0.2.10", "%2Fmnt%2FMPD%2Fcover.jpg")
        self.assertEqual(result, "http://192.0.2.10/%2Fmnt%2FMPD%2Fcover.jpg")


if __name__ == "__main__":
    unittest.main()
