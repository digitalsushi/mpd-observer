import unittest
from unittest.mock import patch
from oil_vision import read_level


class OilConsensusTests(unittest.TestCase):
    def read(self, values):
        results = [ValueError('missing') if v is None else
                   {'percent_of_gauge_scale': v} for v in values]
        with patch('oil_vision.measure', side_effect=results):
            return read_level(None)

    def test_partial_needle_outlier(self):
        result = self.read([54.01, 62.22, 63.02, 62.51])
        self.assertEqual(result['percent'], 63)
        self.assertLessEqual(result['spread'], 2)

    def test_full_agreement(self):
        self.assertEqual(self.read([62.5, 62.6, 62.7, 62.8])['percent'], 63)

    def test_only_two_agree(self):
        with self.assertRaises(ValueError):
            self.read([54, 55, 62, 63])

    def test_not_enough_detections(self):
        with self.assertRaises(ValueError):
            self.read([None, None, 62, 63])

    def test_three_valid_detections(self):
        self.assertEqual(self.read([None, 62.5, 63, 63.2])['percent'], 63)

    def test_disagreement(self):
        with self.assertRaises(ValueError):
            self.read([20, 40, 60, 80])


if __name__ == '__main__':
    unittest.main()
