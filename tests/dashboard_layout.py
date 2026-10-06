"""Browser-assisted DOM check, stdlib only.

Run: python3 tests/dashboard_layout.py --port 7013
Open the printed URL in a browser with classic scrollbars; reload at viewports
320, 335, 768 and 1280 x 800. Missing measurements/timeouts fail, never skip.
The dashboard's actual HTML/CSS/JS and snapshot renderer are used; personal
session collection is disabled. This check is separate from unittest discovery.
"""
import argparse
import json
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import dashboard

WIDTHS = (320, 335, 768, 1280)
CHECK = b"""
const check = setInterval(() => {
  if (document.getElementById('dashboard-content').getAttribute('aria-busy') !== 'false') return;
  clearInterval(check);
  requestAnimationFrame(() => requestAnimationFrame(() => {
    const root = document.documentElement;
    const box = document.body.getBoundingClientRect();
    const sample = {
      width: innerWidth, height: innerHeight, client: root.clientWidth,
      scroll: root.scrollWidth, vertical: root.scrollHeight > root.clientHeight,
      body: box.width, bodyOverflow: getComputedStyle(document.body).overflowX,
      rootOverflow: getComputedStyle(root).overflowX,
      numbers: [...document.querySelectorAll('.causal-grid strong')].map(el => ({
        client: el.clientWidth, scroll: el.scrollWidth,
        visible: el.checkVisibility({checkOpacity: true, checkVisibilityCSS: true}),
        height: el.getBoundingClientRect().height,
        right: el.getBoundingClientRect().right
      }))
    };
    fetch('/layout-result', {method: 'POST', body: JSON.stringify(sample)}).then(response => {
      if (response.ok) document.body.dataset.layoutObserved = String(sample.width);
    });
  }));
}, 50);
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    if not __debug__:
        parser.error("optimized Python is unsupported; unset PYTHONOPTIMIZE and omit -O/-OO")
    parser.add_argument("--port", type=int, default=7013)
    args = parser.parse_args()
    samples, completed = {}, threading.Event()
    with tempfile.TemporaryDirectory(prefix="007-layout-") as tmp:
        server = dashboard.create_server(
            "127.0.0.1", args.port, Path(tmp) / "empty-registry.json",
            ROOT / "dashboard", activity_provider=lambda _entries: {},
        )
        base = server.RequestHandlerClass

        class Handler(base):
            def do_GET(self):
                if self.path in ("/", "/layout-check.js"):
                    payload = CHECK if self.path.endswith(".js") else (
                        (ROOT / "dashboard/index.html").read_bytes().replace(
                            b"</body>", b'<script src="/layout-check.js"></script></body>'
                        )
                    )
                    self.send_response(200)
                    self.send_common_headers(
                        "text/javascript" if self.path.endswith(".js") else "text/html",
                        len(payload),
                    )
                    self.end_headers()
                    self.wfile.write(payload)
                else:
                    super().do_GET()

            def do_POST(self):
                if self.path != "/layout-result":
                    self.json_response(404, {"error": "not found"})
                    return
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    self.json_response(400, {"error": "invalid length"})
                    return
                sample = json.loads(self.rfile.read(length))
                samples[sample["width"]] = sample
                self.json_response(200, {"observed": True})
                if all(width in samples for width in WIDTHS):
                    completed.set()

            def send_common_headers(self, content_type, length, cache="no-store"):
                super().send_common_headers(content_type, length, "no-store")

        server.RequestHandlerClass = Handler
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print(f"LAYOUT_URL=http://127.0.0.1:{server.server_port}/", flush=True)
        try:
            assert completed.wait(180), f"missing browser widths: {set(WIDTHS) - samples.keys()}"
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
        print(json.dumps(samples, sort_keys=True), flush=True)
        for width in WIDTHS:
            sample = samples[width]
            assert sample["height"] == 800 and sample["vertical"], sample
            assert width - sample["client"] > 0, "classic scrollbar required"
            assert sample["scroll"] <= sample["client"], sample
            assert sample["body"] <= sample["client"], sample
            assert sample["bodyOverflow"] not in ("hidden", "clip"), sample
            assert sample["rootOverflow"] not in ("hidden", "clip"), sample
            assert len(sample["numbers"]) == 4, sample
            assert all(
                number["visible"] and number["height"] > 0
                and 0 < number["client"] >= number["scroll"]
                and 0 < number["right"] <= sample["client"]
                for number in sample["numbers"]
            ), sample
        print("PASS: four real DOM widths, no page overflow or clipped causal numbers")


if __name__ == "__main__":
    main()
