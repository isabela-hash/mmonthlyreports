#!/usr/bin/env python3
"""Reserve snapshot IDs and install private configuration in Drive.

Run after sharing an existing PRIVATE Drive folder with the service account.
The command does not change sharing or create platform permissions.
"""
import argparse
import io
import json
import os
import sys
from pathlib import Path
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.benchmarks.core import validate_config
from tools.benchmarks.storage import drive_service, read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Private local config JSON, never commit")
    parser.add_argument("--start", required=True, help="First generation month YYYY-MM")
    parser.add_argument("--months", type=int, default=24)
    parser.add_argument("--revisions", type=int, default=3)
    parser.add_argument("--config-drive-id", help="Update existing configuration; omit for first installation")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    validate_config(config)
    year, month = map(int, args.start.split("-"))
    if not 1 <= month <= 12 or not 1 <= args.months <= 120 or not 1 <= args.revisions <= 10:
        raise ValueError("Invalid reservation range")
    drive = drive_service()
    # Reject folders with broad link/public permissions. Existing specific-user access is preserved.
    permissions = drive.permissions().list(fileId=config["folder_id"], fields="permissions(type)", supportsAllDrives=True).execute()
    if any(p["type"] in ("anyone", "domain") for p in permissions.get("permissions", [])):
        raise ValueError("Use a private folder without domain-wide or public-link sharing")
    slots = config.setdefault("slots", {})
    if args.config_drive_id:
        existing = read_json(drive, args.config_drive_id)
        if existing["folder_id"] != config["folder_id"]:
            raise ValueError("Configuration must preserve its snapshot folder")
        for report_id, file_id in existing.get("slots", {}).items():
            if report_id in slots and slots[report_id] != file_id:
                raise ValueError("Existing snapshot reservations cannot be replaced")
            slots[report_id] = file_id
    pending = []
    for offset in range(args.months):
        n = year * 12 + month - 1 + offset
        for revision in range(1, args.revisions + 1):
            report_id = f"{n // 12:04d}-{n % 12 + 1:02d}-r{revision}"
            if report_id not in slots:
                pending.append(report_id)
    # Keep reservations in the private config so concurrent monthly runs use the same IDs.
    for start in range(0, len(pending), 1000):
        batch = pending[start:start + 1000]
        ids = drive.files().generateIds(count=len(batch), space="drive", type="files").execute()["ids"]
        slots.update(zip(batch, ids))
    raw = json.dumps(config, indent=2).encode()
    from googleapiclient.http import MediaIoBaseUpload
    media = MediaIoBaseUpload(io.BytesIO(raw), mimetype="application/json")
    if args.config_drive_id:
        result = drive.files().update(fileId=args.config_drive_id, media_body=media, fields="id", supportsAllDrives=True).execute()
    else:
        result = drive.files().create(body={"name": "country-benchmark-config.json", "parents": [config["folder_id"]]}, media_body=media, fields="id", supportsAllDrives=True).execute()
    fd = os.open(args.config, os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
    os.chmod(args.config, 0o600)
    print(json.dumps({"config_drive_id": result["id"], "reserved_reports": len(slots)}))


if __name__ == "__main__":
    main()
