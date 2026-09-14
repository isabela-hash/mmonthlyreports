#!/usr/bin/env python3
"""Generate immutable reports or validate dated JSON/CSV source exports."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
import secrets
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.benchmarks.core import snapshot, six_months
from tools.benchmarks.storage import DriveStore, load_config
from tools.benchmarks.sources import collect


def password_hash(password):
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f"{salt}:{digest}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=None, help="Generation date; default today in Madrid")
    parser.add_argument("--revision", default=1, type=int)
    parser.add_argument("--input", help="Dated normalized JSON bundle or CSV; local development/import")
    parser.add_argument("--metadata", help="JSON metadata with fx rates for CSV imports")
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--password-output", help="Private local file for new report passwords; never print in job logs")
    args = parser.parse_args()
    as_of = date.fromisoformat(args.as_of) if args.as_of else datetime.now(ZoneInfo("Europe/Madrid")).date()
    config = load_config()
    store = None
    report_id = f"{as_of:%Y-%m}-r{args.revision}"
    try:
        if not args.audit_only:
            store = DriveStore(config)
            try:
                existing = store.get(report_id)
                print(json.dumps({"status": "already_exists", "id": existing["id"]}))
                return 0
            except FileNotFoundError:
                pass
        if args.input:
            path = Path(args.input)
            if path.suffix.lower() == ".csv":
                bundle = json.loads(Path(args.metadata).read_text()) if args.metadata else {}
                bundle["rows"] = list(csv.DictReader(path.open()))
                for row in bundle["rows"]:
                    row["spend_compatible"] = str(row.get("spend_compatible", "")).lower() == "true"
            else:
                bundle = json.loads(path.read_text())
        else:
            store = store or DriveStore(config)
            bundle = collect(config, six_months(as_of), store.drive)
        document = snapshot(bundle, config, as_of, args.revision)
        if args.audit_only:
            print(json.dumps({"status": "validated", "id": document["id"], "rows": len(document["rows"]), "clients_with_data": len({r['client'] for r in document['rows']}), "failures": len(document["failures"])}))
            return 0
        # Root secrets generate distinct memorable passwords for every report/scope.
        from tools.benchmarks.access import report_passwords
        passwords = report_passwords(report_id)
        document["access"] = {view: password_hash(password) for view, password in passwords.items()}
        result = store.put(document)
        if args.password_output:
            fd = os.open(args.password_output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as handle:
                json.dump({"id": report_id, **passwords}, handle)
        print(json.dumps({"status": result, "id": report_id}))
        return 0
    except Exception as exc:
        if store and not args.audit_only:
            store.log_failure(report_id)
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
