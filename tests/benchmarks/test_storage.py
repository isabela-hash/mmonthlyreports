import json
from unittest.mock import MagicMock
import pytest
from googleapiclient.errors import HttpError
from httplib2 import Response
from tools.benchmarks.storage import DriveStore


def test_atomic_create_retries_compare_fingerprints():
    drive = MagicMock()
    store = DriveStore({"folder_id": "folder", "slots": {"2026-09-r1": "reserved"}}, drive)
    document = {"id": "2026-09-r1", "fingerprint": "same"}
    assert store.put(document) == "created"
    assert drive.files().create.call_args.kwargs["body"]["id"] == "reserved"
    drive.files().create().execute.side_effect = HttpError(Response({"status": "409"}), b"already exists")
    drive.files().get_media().execute.return_value = json.dumps(document).encode()
    assert store.put(document) == "already_exists"
    with pytest.raises(ValueError, match="Immutable"):
        store.put({**document, "fingerprint": "changed"})
    drive.files().update.assert_not_called()


def test_missing_report_and_unreserved_revision():
    store = DriveStore({"slots": {}}, MagicMock())
    with pytest.raises(FileNotFoundError): store.get("2026-09-r1")
    with pytest.raises(ValueError): store.get("../config")
    with pytest.raises(ValueError, match="Reserve"): store.put({"id": "2026-09-r1"})
