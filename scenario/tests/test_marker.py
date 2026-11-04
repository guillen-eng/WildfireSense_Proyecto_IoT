"""El control experimental no expone las etiquetas del evento a los detectores."""
import json
import unittest
from runner import publish_scenario_marker


class DummyDelivery:
    def __init__(self):
        self.waited = False
    def wait_for_publish(self, timeout):
        self.waited = True
    def is_published(self):
        return True


class DummyClient:
    def __init__(self):
        self.records = []
        self.info = DummyDelivery()
    def publish(self, topic, payload, qos, retain):
        self.records.append((topic, payload, qos, retain))
        return self.info


class MarkerTests(unittest.TestCase):
    def test_start_marker_has_no_event_label(self):
        client = DummyClient()
        publish_scenario_marker(client, 'start', '20261102T212100123456Z')
        topic, encoded, qos, retained = client.records[0]
        self.assertEqual(topic, 'wildfiresense/scenario/control')
        self.assertEqual(qos, 1)
        self.assertFalse(retained)
        self.assertEqual(json.loads(encoded), {
            'type': 'start', 'run_id': '20261102T212100123456Z'})
        self.assertTrue(client.info.waited)
