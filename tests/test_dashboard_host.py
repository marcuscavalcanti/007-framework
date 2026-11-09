"""HTTP authority controls over synthetic data; no session log reads."""
import http.client
import os
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

import dashboard


class DashboardHostTests(unittest.TestCase):
    def test_dashboard_announces_its_port_when_python_ignores_environment(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            env = {"PATH": os.environ["PATH"], "HOME": temporary, "LANG": "C", "PYTHONUNBUFFERED": "1"}
            process = subprocess.Popen([sys.executable, "-B", "-I", str(root / "bin/007"), "dashboard", "--port", "0",
                                        "--registry", str(Path(temporary) / "registry.json"), "--no-open"],
                                       env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    self.assertTrue(selector.select(5), "dashboard address remained buffered")
                    self.assertRegex(process.stdout.readline(), r"^007 dashboard: http://127\.0\.0\.1:[0-9]+")
            finally:
                try:
                    state = dashboard.framework_cli.kill_process_group(process)
                finally:
                    process.stdout.close()
                    process.stderr.close()
                self.assertEqual(state, "gone")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in ("index.html", "styles.css", "app.js"):
            (self.root / name).write_text("synthetic asset")
        self.server = dashboard.create_server("127.0.0.1", 0, self.root / "registry.json", self.root)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(2)

    def request(self, path, hosts):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        try:
            connection.putrequest("GET", path, skip_host=True)
            for host in hosts:
                connection.putheader("Host", host)
            connection.endheaders()
            response = connection.getresponse()
            response.read()
            return response.status
        finally:
            connection.close()

    def test_foreign_missing_duplicate_and_malformed_hosts_cannot_read_any_route(self):
        port = self.server.server_port
        invalid = [[], ["foreign.invalid:" + str(port)], [f"localhost:{port}", f"127.0.0.1:{port}"],
                   [f"user@localhost:{port}"], [f"localhost:{port}/path"], [f"localhost:{port}#x"],
                   [f"localhost:{port}?x"], ["localhost:999999"], [f"local host:{port}"],
                   ["localhost:1"], ["localhost"], [f"[::1]:{port}"]]
        with mock.patch.object(dashboard, "build_snapshot", return_value={}) as snapshot:
            for path in ("/", "/app.js", "/api/health", "/api/snapshot", "/missing"):
                for hosts in invalid:
                    with self.subTest(path=path, hosts=hosts):
                        self.assertEqual(self.request(path, hosts), 403)
            snapshot.assert_not_called()

    def test_actual_port_loopback_and_canonical_localhost_aliases_remain_usable(self):
        port = self.server.server_port
        with mock.patch.object(dashboard, "build_snapshot", return_value={}) as snapshot:
            for host in (f"127.0.0.1:{port}", f"localhost:{port}", f"LOCALHOST.:{port}"):
                with self.subTest(host=host):
                    self.assertEqual(self.request("/api/health", [host]), 200)
                    self.assertEqual(self.request("/api/snapshot", [host]), 200)
                    self.assertEqual(self.request("/styles.css", [host]), 200)
            self.assertEqual(snapshot.call_count, 3)

    def test_absolute_request_targets_are_rejected_before_snapshot(self):
        host = f"localhost:{self.server.server_port}"
        with mock.patch.object(dashboard, "build_snapshot", return_value={}) as snapshot:
            for target in ("http://foreign.invalid/api/snapshot", "//foreign.invalid/api/snapshot",
                           "http://" + host + "/api/snapshot"):
                with self.subTest(target=target):
                    self.assertEqual(self.request(target, [host]), 400)
            snapshot.assert_not_called()

    def test_explicit_wildcard_bind_still_accepts_the_local_interface_address(self):
        self.close()
        self.server = dashboard.create_server("0.0.0.0", 0, self.root / "registry.json", self.root)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.assertEqual(self.request("/api/health", [f"127.0.0.1:{self.server.server_port}"]), 200)
