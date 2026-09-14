"""Shared Google Workspace service construction.

Supports local OAuth for Codex/dev and service-account credentials for Cloud Run.
"""
from __future__ import annotations

import os
import pickle
import json
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

load_dotenv()

WORKSPACE_SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/spreadsheets",
]

TOKEN_PATH = Path("token_workspace.pickle")
LEGACY_TOKEN_PATH = Path("token.pickle")
CREDS_PATH = Path("credentials.json")


def get_workspace_credentials(
    scopes: Iterable[str] | None = None,
    token_path: Path = TOKEN_PATH,
    creds_path: Path = CREDS_PATH,
) -> Credentials:
    """Return Google credentials for Drive, Slides, and Sheets APIs.

    If GOOGLE_SERVICE_ACCOUNT_FILE is set, the service account is used. Otherwise
    the existing installed-app OAuth flow is used and persisted locally.
    """
    scopes = list(scopes or WORKSPACE_SCOPES)
    service_account_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    service_account_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()

    if service_account_file:
        service_account_path = Path(service_account_file)
        if not service_account_path.exists():
            raise FileNotFoundError(
                "GOOGLE_SERVICE_ACCOUNT_FILE points to a missing file: "
                f"{service_account_path}. Mount a valid service-account JSON in Cloud Run "
                "or unset GOOGLE_SERVICE_ACCOUNT_FILE for local OAuth."
            )
        return service_account.Credentials.from_service_account_file(
            str(service_account_path),
            scopes=scopes,
        )
    if service_account_json:
        return service_account.Credentials.from_service_account_info(
            json.loads(service_account_json),
            scopes=scopes,
        )

    creds = None
    if token_path.exists():
        with open(token_path, "rb") as handle:
            creds = pickle.load(handle)
    elif token_path == TOKEN_PATH and LEGACY_TOKEN_PATH.exists():
        with open(LEGACY_TOKEN_PATH, "rb") as handle:
            creds = pickle.load(handle)

    if creds and hasattr(creds, "has_scopes") and not creds.has_scopes(scopes):
        creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not creds_path.exists():
                raise FileNotFoundError(
                    "Google Workspace credentials not found. For local development, add "
                    f"{creds_path} or an existing token file. For Cloud Run, set "
                    "GOOGLE_SERVICE_ACCOUNT_FILE to a mounted service-account JSON."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), scopes)
            creds = flow.run_local_server(port=0)
        with open(token_path, "wb") as handle:
            pickle.dump(creds, handle)

    return creds


def build_workspace_services(credentials: Credentials | None = None) -> dict:
    """Build Drive, Slides, and Sheets API clients."""
    credentials = credentials or get_workspace_credentials()
    return {
        "drive": build("drive", "v3", credentials=credentials),
        "slides": build("slides", "v1", credentials=credentials),
        "sheets": build("sheets", "v4", credentials=credentials),
    }


def extract_file_id(value: str) -> str:
    """Extract a Drive/Docs/Sheets/Slides file ID from a raw ID or URL."""
    value = value.strip()
    markers = ["/d/", "/folders/", "id="]
    for marker in markers:
        if marker in value:
            tail = value.split(marker, 1)[1]
            for separator in ["/", "?", "&"]:
                tail = tail.split(separator, 1)[0]
            return tail
    return value
