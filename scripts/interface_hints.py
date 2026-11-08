"""Replay prompt interface hints: the public signature lines a commit added or changed in its sources, never bodies (no model)."""
import io
import re
import subprocess
import tokenize

# ponytail: Python def/class signatures only; other languages are out of scope until a non-Python repo is replayed.
SIGNATURE = re.compile(r"^(async\s+)?def\s+[A-Za-z]\w*\s*\(.*|^class\s+[A-Za-z]\w*.*")  # [A-Za-z] first: `_private` names never match
MAX_LINES = 20
GIT_ENV = {"PATH": "/usr/bin:/bin", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "LANG": "C"}
HEADER = "Interface expected by the change (signatures only; implement the behaviour yourself):"


def _added(line):
    return line.startswith("+") and not line.startswith("+++")


def _signature(lines, start):
    """The signature from the consecutive added lines of its hunk, cut at its top-level ':' (Python's own tokenizer, so strings and
    comments cannot fool it): a one-line body never leaks, and a next line is read only while the header is still open."""
    parts, ends = [], {}
    for line in lines[start:start + MAX_LINES]:
        if not _added(line):
            break
        parts.append(line[1:].strip())
        depth, ends = 0, {}
        try:
            for token in tokenize.generate_tokens(io.StringIO("\n".join(parts) + "\n").readline):
                if token.type in (tokenize.COMMENT, tokenize.NL):
                    continue
                if token.type == tokenize.NEWLINE:  # the statement closed without a header ':': keep it as found
                    return _text(parts, ends)
                ends[token.end[0]] = token.end[1]
                if token.type == tokenize.OP and token.string == ":" and depth == 0:
                    return _text(parts, ends)
                if token.type == tokenize.OP:
                    depth += (token.string in ("(", "[", "{")) - (token.string in (")", "]", "}"))
        except (tokenize.TokenError, SyntaxError):  # still open (or unreadable): only the tokens read so far are kept
            pass
    return _text(parts, ends) + " …"


def _text(parts, ends):
    return " ".join(parts[row - 1][:end] for row, end in sorted(ends.items()))


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
