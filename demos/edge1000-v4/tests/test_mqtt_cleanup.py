"""Regression tests for Paho socket teardown in the 1000-client simulator."""
import selectors
import socket
import unittest
from lab.mqtt_run import Pool, _safe_modify


class TestMQTTCleanup(unittest.TestCase):
    def test_late_unregister_is_safe(self):
        selector = selectors.DefaultSelector()
        a, b = socket.socketpair()
        try:
            # Race: close callback removed the socket before Paho unregisters write.
            _safe_modify(selector, a, selectors.EVENT_READ, object())
            selector.register(a, selectors.EVENT_READ)
            _safe_modify(selector, a, selectors.EVENT_READ | selectors.EVENT_WRITE, None)
            self.assertEqual(selector.get_key(a).events,
                             selectors.EVENT_READ | selectors.EVENT_WRITE)
            selector.unregister(a)
            _safe_modify(selector, a, selectors.EVENT_READ, None)
            selector.close()
            _safe_modify(selector, a, selectors.EVENT_READ, None)
        finally:
            selector.close()
            a.close()
            b.close()

    def test_close_disables_paho_socket_callbacks(self):
        class FakeClient:
            def __init__(self):
                self.disconnected = False
                self.on_socket_open = lambda *args: None
                self.on_socket_close = lambda *args: None
                self.on_socket_register_write = lambda *args: None
                self.on_socket_unregister_write = lambda *args: None

            def disconnect(self):
                self.disconnected = True

        pool = Pool.__new__(Pool)
        pool.selector = selectors.DefaultSelector()
        pool.clients = [FakeClient() for _ in range(1000)]
        pool.close()
        self.assertTrue(all(c.disconnected for c in pool.clients))
        self.assertTrue(all(c.on_socket_unregister_write is None for c in pool.clients))
        self.assertIsNone(pool.selector.get_map())


if __name__ == "__main__":
    unittest.main()
