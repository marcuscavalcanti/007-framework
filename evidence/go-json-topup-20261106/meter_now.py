"""Latest Codex weekly meter reading in the local rollouts: numeric fields only. Lab cells run --ephemeral with their own
CODEX_HOME, so this shows the account meter only when some interactive session logged it; the timestamp says how fresh it is."""
import json
from pathlib import Path
best = None
for f in sorted((Path.home() / ".codex" / "sessions").glob("*/*/*/*.jsonl"), key=lambda p: p.stat().st_mtime)[-20:]:
    for line in f.open(errors="replace"):
        try:
            o = json.loads(line)
        except ValueError:
            continue
        p = o.get("payload") if isinstance(o, dict) else None
        if isinstance(p, dict) and p.get("type") == "token_count":
            for key in ("primary", "secondary"):
                r = (p.get("rate_limits") or {}).get(key) or {}
                if r.get("window_minutes") == 10080 and isinstance(r.get("used_percent"), (int, float)):
                    if best is None or o["timestamp"] > best[0]:
                        best = (o["timestamp"], r["used_percent"], r.get("resets_at"))
print(json.dumps({"reading_at": best[0], "weekly_used_percent": best[1], "resets_at": best[2]} if best else {"reading_at": None}))
