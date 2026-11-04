"""Pruebas de aislamiento y evaluación básica del modo sombra."""
import json
import unittest
from shadow_monitor import ShadowMonitor


class ShadowMonitorTests(unittest.TestCase):
    def test_ignora_topico_sos(self):
        monitor = ShadowMonitor()
        lines = monitor.process("wildfiresense/events/sos", b'{}')
        self.assertEqual(lines, [])
        self.assertEqual(monitor.readings, 0)

    def test_payload_invalido_no_rompe_servicio(self):
        monitor = ShadowMonitor()
        outputs = monitor.process("wildfiresense/readings/a", b'{')
        self.assertEqual(monitor.invalid_json, 1)
        self.assertIn('SHADOW_INVALID_JSON', outputs[0])

    def test_historial_por_sensor(self):
        monitor = ShadowMonitor()
        for _ in range(20):
            for node in ('A', 'B'):
                msg = {'node_id':node,'measurements':{'air_temperature_c':20.0}}
                self.assertEqual([], [x for x in monitor.process('wildfiresense/readings/'+node, json.dumps(msg).encode()) if x.startswith('CUSUM_SHADOW')])
        self.assertEqual(set(monitor.detectors['sensible'].baseline), {'A','B'})

    def test_sombra_detecta_sin_publicar(self):
        monitor = ShadowMonitor()
        msg = {'node_id':'A','timestamp':'2024-11-09T00:00:00Z', 'measurements':{'air_temperature_c':20.0}}
        for _ in range(20):
            monitor.process('wildfiresense/readings/A', json.dumps(msg).encode())
        msg['measurements']['air_temperature_c'] = 30.0
        lines = []
        for _ in range(10):
            lines.extend(monitor.process('wildfiresense/readings/A', json.dumps(msg).encode()))
        self.assertTrue(any(x.startswith('CUSUM_SHADOW ') for x in lines))
        # La clase no dispone de ninguna función de publicación MQTT.
        self.assertFalse(hasattr(monitor, 'publish'))


if __name__ == '__main__':
    unittest.main()
