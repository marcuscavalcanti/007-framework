"""AMENDMENT-2: every 007 module of the pilot comes from the v1.7.0 distribution, checked against its own manifest first.
Import this before anything else; it refuses to run if a 007 module was already loaded from somewhere else."""
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PINNED = HERE.parent.parent / "qualified-releases" / "v1.7.0-21ba2ffba46a"
COMMIT, MANIFEST_SHA256 = "21ba2ffba46a0e0cd6be0616a5582ffcffb24d88", "987d3cb746a4001f51d07456f5470bdd79d0d172b41b8275e3e23e477da0f8f9"
EVALUATOR_SHA256 = "362f40c79c52af94db62e8b127a214f0dac0a701736c3ffd3a92fc42b783c6be"  # lab_accept.py embedded in every mined task


def verify():
    manifest = PINNED / "evidence" / "v1.7.0" / "manifest.sha256"
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != MANIFEST_SHA256:
        raise SystemExit(f"pinned manifest differs: {manifest}")
    for line in manifest.read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        if hashlib.sha256((PINNED / name).read_bytes()).hexdigest() != digest:
            raise SystemExit(f"pinned file differs from the v1.7.0 manifest: {name}")


def load():
    verify()
    scripts = str(PINNED / "scripts")
    stray = [m for m in ("effort_lab", "replay_eval", "native_runner", "harness_report") if m in sys.modules
             and not str(getattr(sys.modules[m], "__file__", "")).startswith(scripts)]
    if stray:
        raise SystemExit(f"007 modules already loaded from elsewhere: {stray}")
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
    print("pinned v1.7.0 ok")
