"""Replay prompt interface hints: the public signature lines a commit added or changed in its sources, never bodies (no model)."""
import re
import subprocess

# ponytail: Python def/class signatures only; other languages are out of scope until a non-Python repo is replayed.
SIGNATURE = re.compile(r"^(async\s+)?def\s+[A-Za-z]\w*\s*\(.*|^class\s+[A-Za-z]\w*.*")  # [A-Za-z] first: `_private` names never match
COMMENT = re.compile(r"\s+#[^\"']*$")  # ponytail: a comment holding a quote is kept; worst case a garbled hint, never a body line
MAX_LINES = 20
GIT_ENV = {"PATH": "/usr/bin:/bin", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "LANG": "C"}
HEADER = "Interface expected by the change (signatures only; implement the behaviour yourself):"


def _added(line):
    return line.startswith("+") and not line.startswith("+++")


def _signature(lines, start):
    """Join a multi-line signature from the consecutive added lines of its hunk, up to the line ending with ':'."""
    parts = []
    for line in lines[start:start + MAX_LINES]:
        if not _added(line):
            break
        text = line[1:].strip()
        code = COMMENT.sub("", text)
        # one-liners (`def f(x): return x`) and closed lines stay single: an unclosed bracket is required before following lines are read
        if not parts and (code.endswith(":") or code.count("(") + code.count("[") <= code.count(")") + code.count("]")):
            return text
        if code:
            parts.append(code)
        if code.endswith(":"):
            return " ".join(parts)
    return " ".join(parts) + " …"


def hints(repo, parent, commit, sources):
    diff = subprocess.run(["git", "-C", str(repo), "diff", "--no-color", "--no-ext-diff", "--unified=0", parent, commit, "--", *sources],
                          capture_output=True, env=GIT_ENV, timeout=120, check=True).stdout.decode()
    lines, found, path = diff.splitlines(), set(), None
    for index, line in enumerate(lines):
        if line.startswith("+++ b/"):
            path = line[6:]
        elif _added(line) and SIGNATURE.match(line[1:].strip()):
            found.add(f"{path}: {_signature(lines, index)}")
    return sorted(found)


def with_hints(text, hints):
    return "\n".join([text, "", HEADER, *("- " + hint for hint in hints)]) if hints else text
