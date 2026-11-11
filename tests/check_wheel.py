"""Verify a built wheel through an isolated installed CLI and synthetic project."""

import argparse
import configparser
from email.parser import Parser
import hashlib
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import ProxyHandler, build_opener
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from framework_cli import kill_process_group, version
from replay_eval import run as run_installer

if sys.flags.optimize:
    raise SystemExit("wheel verification requires non-optimized Python")

urlopen = build_opener(ProxyHandler({})).open


def check(wheel, use_pipx=False):
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        metadata = next(name for name in names if name.endswith(".dist-info/entry_points.txt"))
        entrypoints = configparser.ConfigParser()
        entrypoints.read_string(archive.read(metadata).decode())
        assert entrypoints["console_scripts"]["007"] == "seven_framework._entrypoint:main"
        package_metadata = Parser().parsestr(archive.read(metadata.replace("entry_points.txt", "METADATA")).decode())
        assert package_metadata["Name"] == "007-framework"
        assert package_metadata["Version"] == version()
        assert not package_metadata.get_all("Requires-Dist")
        for relative in ("SKILL.md", "dashboard/index.html", "dashboard/app.js", "dashboard/styles.css",
                         "evidence/v1.4.0/causal-roi-result.json", "scripts/lab_accept.py"):
            assert archive.read("seven_framework/" + relative) == (ROOT / relative).read_bytes()
        assert all(name.startswith(("seven_framework/", "007_framework-")) for name in names)

    with tempfile.TemporaryDirectory(prefix="007-installed-smoke-") as temporary:
        root = Path(temporary)
        home = root / "home"; home.mkdir()
        env = {"PATH": os.environ["PATH"], "HOME": str(home), "LANG": "C", "PYTHONUNBUFFERED": "1",
               "PYTHONDONTWRITEBYTECODE": "1", "PIP_CONFIG_FILE": os.devnull,
               "PIP_DISABLE_PIP_VERSION_CHECK": "1", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
        if use_pipx:
            env.update(PIPX_HOME=str(root / "pipx"), PIPX_BIN_DIR=str(root / "bin"), PIPX_MAN_DIR=str(root / "man"))
            run_installer([sys.executable, "-m", "pipx", "install", "--python", sys.executable, str(wheel)],
                          cwd=root, env=env, timeout=180).check_returncode()
            cli = root / "bin/007"
        else:
            virtual = root / "venv"
            venv.EnvBuilder(with_pip=False).create(virtual)
            python = virtual / "bin/python"
            run_installer([sys.executable, "-m", "pip", "--python", str(python), "install", "--no-index", "--no-deps", str(wheel)],
                          cwd=root, env=env, timeout=120).check_returncode()
            cli = virtual / "bin/007"

        def run(*args):
            return subprocess.check_output([str(cli), *map(str, args)], cwd=root, env=env, text=True, timeout=30)

        assert run("--version").strip() == "007 " + version()
        repo = root / "project"; repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], env=env, check=True, timeout=30)
        registry = root / "registry.json"
        run("init", "--repo", repo, "--registry", registry)
        run("begin", "--repo", repo, "--task-id", "synthetic-package-smoke")
        receipt = json.loads((ROOT / "examples/task.receipt.example.json").read_text())
        receipt.update(task_id="synthetic-package-smoke", requested_provider="fixture", served_provider="fixture",
                       requested_model="fixture", served_model="fixture", cost_source="custom:synthetic-smoke",
                       uncertainty="Synthetic packaging fixture, no model inference or economic evidence")
        receipt_file = root / "synthetic.receipt.json"
        receipt_file.write_text(json.dumps(receipt))
        run("record", "--repo", repo, "--file", receipt_file)
        assert (repo / ".007/receipts/synthetic-package-smoke.receipt.json").is_file()

        process = subprocess.Popen([str(cli), "dashboard", "--port", "0", "--registry", str(registry), "--no-open"],
                                   cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   start_new_session=True)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                assert selector.select(15), "installed dashboard did not announce its address"
                address = process.stdout.readline().strip()
            prefix = "007 dashboard: http://127.0.0.1:"
            assert address.startswith(prefix) and address[len(prefix):].isdigit()
            base = address.removeprefix("007 dashboard: ")
            for route in ("/", "/app.js", "/styles.css", "/api/health"):
                with urlopen(base + route, timeout=5) as response:
                    assert response.status == 200
            deadline = time.monotonic() + 15
            while True:
                try:
                    with urlopen(base + "/api/snapshot", timeout=5) as response:
                        snapshot = json.load(response)
                    break
                except HTTPError as error:
                    error.close()
                    if error.code != 503 or time.monotonic() >= deadline:
                        raise
                    time.sleep(0.05)
            assert snapshot["aggregate"]["tasks"] == 1
            assert snapshot["causal_evidence"] == json.loads((ROOT / "evidence/v1.4.0/causal-roi-result.json").read_text())
        finally:
            try:
                state = kill_process_group(process)
            finally:
                process.stdout.close()
                process.stderr.close()
            assert state == "gone", "installed dashboard cleanup is unconfirmed"
    print(json.dumps({"proof": "synthetic-installed-cli-smoke", "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                      "installer": "pipx" if use_pipx else "pip",
                      "version": version(), "commands": ["version", "init", "begin", "record", "dashboard"],
                      "dashboard_assets_and_causal_evidence": "byte-preserved"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--pipx", action="store_true")
    args = parser.parse_args()
    check(args.wheel.resolve(), args.pipx)
