import json
import tempfile
import unittest
from pathlib import Path
from shadow_monitor import ShadowSessionRecorder

RUN = '20261102T212100123456Z'


class ShadowSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)
        (self.out / RUN).mkdir()
        self.runtime = ShadowSessionRecorder(self.out)

    def test_crea_archivo_y_termina_resumen(self):
        self.assertIn('SHADOW_SESSION_START', self.runtime.on_control(
            json.dumps({'type': 'start', 'run_id': RUN}).encode())[0])
        message = {'node_id': 'A', 'timestamp': '2024-11-09T01:02:00+00:00',
                   'measurements': {'air_temperature_c': 20.0}}
        for _ in range(20):
            self.runtime.on_reading('wildfiresense/readings/A', json.dumps(message).encode())
        message['measurements']['air_temperature_c'] = 30.0
        for _ in range(10):
            self.runtime.on_reading('wildfiresense/readings/A', json.dumps(message).encode())
        self.runtime.on_control(json.dumps({'type': 'end', 'run_id': RUN}).encode())
        output = (self.out / RUN / 'shadow_events.jsonl').read_text(encoding='utf-8')
        self.assertIn('"shadow_only": true', output)
        self.assertIn('"run_id": "' + RUN + '"', output)
        summary = json.loads((self.out / RUN / 'shadow_summary.json').read_text())
        self.assertEqual(summary['readings_received'], 30)
        self.assertTrue(summary['session_closed'])

    def test_sin_inicio_no_crea_fichero(self):
        msg = b'{"node_id":"A","measurements":{"air_temperature_c":20}}'
        self.assertEqual([], self.runtime.on_reading('wildfiresense/readings/A', msg))
        self.assertFalse((self.out / RUN / 'shadow_events.jsonl').exists())

    def test_rechaza_run_id_inseguro(self):
        response = self.runtime.on_control(b'{"type":"start","run_id":"../../etc"}')
        self.assertIn('SHADOW_BAD_CONTROL', response[0])
        self.assertIsNone(self.runtime.run_id)

    def test_nuevo_run_reinicia_detector(self):
        self.runtime.on_control(json.dumps({'type': 'start', 'run_id': RUN}).encode())
        msg = b'{"node_id":"A","measurements":{"air_temperature_c":20}}'
        self.runtime.on_reading('wildfiresense/readings/A', msg)
        self.runtime.on_control(json.dumps({'type': 'end', 'run_id': RUN}).encode())
        next_id = '20261102T212101123456Z'
        (self.out / next_id).mkdir()
        self.runtime.on_control(json.dumps({'type': 'start', 'run_id': next_id}).encode())
        self.assertEqual(self.runtime.monitor.readings, 0)
