import unittest

from mpd_observer.weather import classify_weather_code, severe_weather_alert


class WeatherTests(unittest.TestCase):
    def test_clear(self):
        self.assertEqual(classify_weather_code(0), "clear")

    def test_cloud_and_fog(self):
        self.assertEqual(classify_weather_code(3), "cloud")
        self.assertEqual(classify_weather_code(45), "cloud")

    def test_rain_and_snow_use_precipitation_icon(self):
        self.assertEqual(classify_weather_code(61), "rain")
        self.assertEqual(classify_weather_code(75), "rain")

    def test_thunder(self):
        self.assertEqual(classify_weather_code(95), "thunder")

    def test_severe_forecast_alerts_for_thunder_or_heavy_rain(self):
        self.assertTrue(severe_weather_alert([0, 3, 95]))
        self.assertTrue(severe_weather_alert([1, 65]))
        self.assertTrue(severe_weather_alert([82]))

    def test_severe_forecast_ignores_light_and_moderate_rain(self):
        self.assertFalse(severe_weather_alert([0, 3, 61, 63, 80, 81]))


if __name__ == "__main__":
    unittest.main()
