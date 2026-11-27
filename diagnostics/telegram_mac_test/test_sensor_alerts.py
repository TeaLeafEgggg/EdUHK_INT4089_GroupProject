from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from sensor_alerts import SensorAlerts, parse_ambient


class SensorAlertTests(unittest.TestCase):
    def setUp(self):
        settings = TemporaryDirectory()
        self.addCleanup(settings.cleanup)
        status_dir = patch('sensor_alerts.status_data.STATUS_DIR', Path(settings.name))
        status_dir.start()
        self.addCleanup(status_dir.stop)

    def test_strict_limits_use_ambient_not_object(self):
        sent = []
        alerts = SensorAlerts(sent.append)
        alerts.process('Ambient: 55.0 C | Object: 80.0 C')
        self.assertEqual(sent, [])
        alerts.process('Water A0: 81 | Ambient: 55.1 C | Object: 21.0 C')
        self.assertEqual(sent, ['Do not touch! Heat warning: the detected temperature is 55.1°C.'])

    def test_one_message_per_episode_and_rearm_after_three_clear_readings(self):
        sent = []
        alerts = SensorAlerts(sent.append)
        hot = 'Ambient: 58.0 C | Object: 29.0 C'
        cool = 'Ambient: 25.0 C | Object: 29.0 C'
        for line in (cool, hot, hot, cool, cool, hot, cool, cool, cool, hot):
            alerts.process(line)
        self.assertEqual(len(sent), 2)

    def test_legacy_water_values_cannot_trigger_an_alert(self):
        sent = []
        alerts = SensorAlerts(sent.append)
        alerts.process('Water A0: 1023 | MLX90614 read failed')
        alerts.process('Water A0: 1023 | Ambient: 25.0 C | Object: 90.0 C')
        self.assertEqual(sent, [])
        self.assertIsNone(parse_ambient('Unrelated serial text'))

    def test_temperature_override_applies_only_to_ambient_threshold(self):
        sent = []
        alerts = SensorAlerts(sent.append, temperature_threshold=30)
        alerts.process('Water A0: 80 | Ambient: 30.0 C | Object: 60.0 C')
        self.assertEqual(sent, [])
        alerts.process('Water A0: 80 | Ambient: 30.1 C | Object: 21.0 C')
        self.assertEqual(sent, ['Do not touch! Heat warning: the detected temperature is 30.1°C.'])


if __name__ == '__main__':
    unittest.main()
