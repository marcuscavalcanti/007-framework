"""PREREG-F: every 007 module comes from the published 1.8.1 distribution, checked against its own manifest first."""
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PINNED = HERE.parents[1] / "qualified-releases" / "v1.8.1-f05ebcbc4749"
COMMIT, MANIFEST_SHA256 = "f05ebcbc47496bcd39c272fe2d0dd82d9a336879", "e064bdeaeda8ebf046711f1ff82e1025c21169b3f91e32fef13db75b4b7d9615"


def verify():
    manifest = PINNED / "evidence" / "v1.8.1" / "manifest.sha256"
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != MANIFEST_SHA256:
        raise SystemExit(f"pinned manifest differs: {manifest}")
    for line in manifest.read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        if hashlib.sha256((PINNED / name).read_bytes()).hexdigest() != digest:
            raise SystemExit(f"pinned file differs from the 1.8.1 manifest: {name}")


def load():
    verify()
    scripts = str(PINNED / "scripts")
    if any(m in sys.modules and not str(getattr(sys.modules[m], "__file__", "")).startswith(scripts) for m in ("effort_lab", "replay_eval")):
        raise SystemExit("007 modules already loaded from elsewhere")
    sys.path.insert(0, scripts)
    import effort_lab
    return effort_lab



def check_loaded():
    """After every import: each 007 module in memory comes from the pinned distribution."""
    scripts = PINNED / "scripts"
    names = {p.stem for p in scripts.glob("*.py")}
    stray = {n: m.__file__ for n, m in list(sys.modules.items()) if n in names and not str(getattr(m, "__file__", "")).startswith(str(scripts))}
    if stray:
        raise SystemExit(f"non-pinned 007 modules loaded: {stray}")


if __name__ == "__main__":
    verify()
    print("pinned 1.8.1 ok")
