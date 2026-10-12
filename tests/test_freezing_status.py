import ast
import math
from pathlib import Path
import unittest


# Isolate the pure rule from Sora's existing server-only dependencies.
source = Path(__file__).resolve().parents[1] / 'deployment/miso/cards/server.py'
tree = ast.parse(source.read_text())
function = next(node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == 'freezing_status')
namespace = {'math': math}
exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
freezing_status = namespace['freezing_status']


class FreezingStatusTests(unittest.TestCase):
    def test_continuous_hour_of_rounded_32(self):
        status = freezing_status(32, {}, 1000)
        for now in range(1030, 4600, 30):
            status = freezing_status(32.49, status, now)
            self.assertEqual(status['state'], 'normal')
        self.assertEqual(freezing_status(32, status, 4600)['state'], 'plateau')

    def test_below_freezing_is_immediate(self):
        self.assertEqual(freezing_status(31.99, {}, 1000)['state'], 'below')

    def test_warming_and_missing_readings_reset_timer(self):
        previous = {'since': 1000, 'checkedAt': 4600}
        for value in (32.5, None, float('nan')):
            self.assertIsNone(freezing_status(value, previous, 4630)['since'])

    def test_gap_and_backward_clock_restart_timer(self):
        previous = {'since': 1000, 'checkedAt': 4600}
        for now in (4691, 900):
            status = freezing_status(32, previous, now)
            self.assertEqual(status['since'], now)
            self.assertEqual(status['state'], 'normal')

    def test_ice_clears_only_after_continuous_warm_hour(self):
        status = freezing_status(31, {}, 1000)
        status = freezing_status(33, status, 1030)
        for now in range(1060, 4630, 30):
            status = freezing_status(33, status, now)
            self.assertEqual(status['state'], 'below')
        self.assertEqual(freezing_status(33, status, 4630)['state'], 'normal')

    def test_boundary_resumes_transition_after_freezing(self):
        status = freezing_status(31, {}, 1000)
        self.assertEqual(freezing_status(32, status, 1030)['state'], 'plateau')

    def test_missing_observation_breaks_warm_hour(self):
        status = freezing_status(33, {'state': 'below', 'checkedAt': 1000}, 1030)
        status = freezing_status(None, status, 1060)
        self.assertEqual(status['state'], 'below')
        self.assertIsNone(status['warmSince'])
        self.assertEqual(freezing_status(33, status, 1090)['warmSince'], 1090)
