#!/usr/bin/env python3
"""Release gate: local datasets/credentials must never enter Next.js traces."""
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
forbidden_dirs = {"data", "output", ".venv", ".git"}
forbidden_names = {"credentials.json", "token.pickle", "token_workspace.pickle"}
traces = list((root / ".next/server").rglob("*.nft.json"))
if not traces:
    raise SystemExit("Build the portal before checking bundle privacy")
violations = 0
for trace in traces:
    for name in json.loads(trace.read_text()).get("files", []):
        path = (trace.parent / name).resolve()
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if relative.parts[0] in forbidden_dirs or path.name in forbidden_names or path.name.startswith(".env") or "service-account" in path.name:
            violations += 1
if violations:
    raise SystemExit(f"Bundle privacy check failed: {violations} private local file references")
print(f"Bundle privacy check passed ({len(traces)} traces)")
