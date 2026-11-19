import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pdc", HERE / "pdc.py")
pdc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pdc)


class HelperTests(unittest.TestCase):
    def test_loopback_ipv4(self):
        self.assertTrue(pdc.is_loopback_ip("127.0.0.1"))

    def test_loopback_ipv6(self):
        self.assertTrue(pdc.is_loopback_ip("::1"))

    def test_public_ip(self):
        self.assertFalse(pdc.is_loopback_ip("192.0.2.1"))

    def test_localhost_names(self):
        self.assertTrue(pdc.hostname_is_localhost("localhost"))
        self.assertTrue(pdc.hostname_is_localhost("mx.localhost."))
        self.assertFalse(pdc.hostname_is_localhost("mail.example.org"))


if __name__ == "__main__":
    unittest.main()
