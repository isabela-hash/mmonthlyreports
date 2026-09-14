"""Private Drive storage; preallocated IDs make creation atomic and retry-safe."""
from __future__ import annotations
import io
import json
import os
from pathlib import Path
from tools.benchmarks.core import REPORT_ID


def drive_service():
    # Never start an interactive OAuth flow from a web request or scheduled job.
    if not any(os.environ.get(k) for k in ("GOOGLE_SERVICE_ACCOUNT_FILE", "GOOGLE_SERVICE_ACCOUNT_JSON")) and not Path("token_workspace.pickle").exists() and not Path("token.pickle").exists():
        raise RuntimeError("Google Drive service credentials are not configured")
    from tools.google_workspace import build_workspace_services
    return build_workspace_services()["drive"]


def read_json(drive, file_id):
    raw = drive.files().get_media(fileId=file_id).execute()
    return json.loads(raw)


def load_config(drive=None):
    path = os.environ.get("BENCHMARK_CONFIG_FILE")
    if path:
        return json.loads(Path(path).read_text())
    file_id = os.environ.get("BENCHMARK_CONFIG_DRIVE_ID")
    if not file_id:
        raise RuntimeError("Benchmark configuration is not installed")
    return read_json(drive or drive_service(), file_id)


class DriveStore:
    def __init__(self, config=None, drive=None):
        self.drive = drive or drive_service()
        self.config = config or load_config(self.drive)

    def get(self, report_id):
        if not REPORT_ID.fullmatch(report_id):
            raise ValueError("Invalid report ID")
        slot = self.config.get("slots", {}).get(report_id)
        if not slot:
            raise FileNotFoundError("Report not available")
        from googleapiclient.errors import HttpError
        try:
            document = read_json(self.drive, slot)
        except HttpError as exc:
            if exc.resp.status == 404:
                raise FileNotFoundError("Report not available") from None
            raise
        if document.get("id") != report_id:
            raise ValueError("Snapshot identity mismatch")
        return document

    def put(self, document):
        from googleapiclient.http import MediaIoBaseUpload
        from googleapiclient.errors import HttpError
        report_id = document["id"]
        slot = self.config.get("slots", {}).get(report_id)
        if not slot:
            raise ValueError("Reserve a Drive ID for this revision before generating")
        raw = json.dumps(document, allow_nan=False).encode()
        try:
            self.drive.files().create(body={"id": slot, "name": f"{report_id}.json", "parents": [self.config["folder_id"]]},
                media_body=MediaIoBaseUpload(io.BytesIO(raw), mimetype="application/json"), fields="id", supportsAllDrives=True).execute()
            return "created"
        except HttpError as exc:
            if exc.resp.status != 409:
                raise
            existing = self.get(report_id)
            if existing["fingerprint"] != document["fingerprint"]:
                raise ValueError("Immutable snapshot exists with different data; create a new revision") from None
            return "already_exists"

    def list_reports(self):
        result, token = [], None
        folder = self.config["folder_id"].replace("'", "\\'")
        while True:
            page = self.drive.files().list(q=f"'{folder}' in parents and trashed = false", fields="nextPageToken,files(id,name)",
                pageToken=token, pageSize=1000, supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
            for item in page.get("files", []):
                report_id = item["name"].removesuffix(".json")
                if REPORT_ID.fullmatch(report_id) and self.config.get("slots", {}).get(report_id) == item["id"]:
                    result.append(report_id)
            token = page.get("nextPageToken")
            if not token:
                return sorted(set(result), reverse=True)

    def log_failure(self, report_id):
        # A new failure record never overwrites the last successful snapshot.
        self.drive.files().create(body={"name": f"failed-{report_id}", "parents": [self.config["folder_id"]],
            "description": "Country benchmark extraction or validation failed. Inspect private Cloud Run logs."}, fields="id", supportsAllDrives=True).execute()
