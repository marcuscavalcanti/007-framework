"""Fail-closed and local-only controls for the installed-wheel verifier."""

import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock
from urllib.request import HTTPHandler
from urllib.response import addinfourl

import check_wheel


class DistributionVerifierTests(unittest.TestCase):
    def test_optimized_python_is_refused_before_wheel_or_installer_access(self):
        result = subprocess.run([sys.executable, "-B", "-O", str(Path(check_wheel.__file__)), "missing.whl"],
                                capture_output=True, text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires non-optimized Python", result.stderr)

    def test_local_http_checks_ignore_the_verifiers_proxy_environment(self):
        seen = []

        def opened(handler, request):
            seen.append((request.host, request.has_proxy()))
            response = addinfourl(io.BytesIO(b"{}"), {}, request.full_url, 200)
            response.msg = "OK"
            return response

        with mock.patch.dict(os.environ, {"http_proxy": "http://proxy.invalid:3128"}, clear=True), \
                mock.patch("urllib.request._opener", None), \
                mock.patch("urllib.request.proxy_bypass", return_value=False), \
                mock.patch.object(HTTPHandler, "http_open", opened):
            with check_wheel.urlopen("http://127.0.0.1:12345/api/health") as response:
                self.assertEqual(response.read(), b"{}")
        self.assertEqual(seen, [("127.0.0.1:12345", False)])
