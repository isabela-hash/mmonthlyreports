from tools import report_ops


class FakeRequest:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class FakeFiles:
    def __init__(self):
        self.created = []
        self.updated = []

    def create(self, body=None, fields=""):
        self.created.append(body)
        return FakeRequest(
            {
                "id": "folder-1",
                "name": body["name"],
                "mimeType": body["mimeType"],
                "webViewLink": "https://drive/folder-1",
                "parents": body.get("parents", []),
            }
        )

    def get(self, **_kwargs):
        return FakeRequest({"parents": ["root-folder"]})

    def update(self, **kwargs):
        self.updated.append(kwargs)
        return FakeRequest({"id": kwargs["fileId"], "webViewLink": "https://sheet"})

    def list(self, **_kwargs):
        return FakeRequest({"files": []})


class FakeDrive:
    def __init__(self):
        self._files = FakeFiles()

    def files(self):
        return self._files


class FakeValues:
    def __init__(self):
        self.appended = []
        self.updated = []

    def append(self, **kwargs):
        self.appended.append(kwargs)
        return FakeRequest({})

    def update(self, **kwargs):
        self.updated.append(kwargs)
        return FakeRequest({})


class FakeSpreadsheets:
    def __init__(self):
        self._values = FakeValues()

    def values(self):
        return self._values


class FakeSheets:
    def __init__(self):
        self._spreadsheets = FakeSpreadsheets()

    def spreadsheets(self):
        return self._spreadsheets


def test_report_ops_create_client_appends_control_row(monkeypatch):
    fake_drive = FakeDrive()
    fake_sheets = FakeSheets()
    ops = report_ops.ReportOps(
        services={"drive": fake_drive, "sheets": fake_sheets},
        control_sheet_id="control-sheet",
    )
    monkeypatch.setattr(ops, "load_clients", lambda active_only=False: [])
    monkeypatch.setattr(report_ops, "ensure_control_sheet_currency_columns", lambda *_args: [])
    monkeypatch.setattr(
        report_ops,
        "_create_data_spreadsheet",
        lambda *_args: {"id": "sheet-1", "webViewLink": "https://docs.google.com/spreadsheets/d/sheet-1/edit"},
    )

    created = ops.create_client(
        "Lux Algo",
        template_presentation_url_or_id="template-1",
        parent_folder_id="root-folder",
    )

    appended = fake_sheets.spreadsheets().values().appended[0]["body"]["values"][0]
    assert created["client_key"] == "lux-algo"
    assert appended[:3] == ["no", "Lux Algo", "lux-algo"]
    assert appended[6:8] == ["Campaigns", "Ads"]
    assert appended[10:] == ["USD", "USD", "none"]


def test_report_ops_set_client_active_updates_active_cell(monkeypatch):
    fake_sheets = FakeSheets()
    ops = report_ops.ReportOps(
        services={"drive": FakeDrive(), "sheets": fake_sheets},
        control_sheet_id="control-sheet",
    )
    monkeypatch.setattr(
        report_ops,
        "read_sheet_values",
        lambda *_args, **_kwargs: [
            ["active", "client_name", "client_key"],
            ["no", "Lux Algo", "lux-algo"],
        ],
    )

    result = ops.set_client_active("lux-algo", True)

    update = fake_sheets.spreadsheets().values().updated[0]
    assert result == {"client_key": "lux-algo", "active": True}
    assert update["range"] == "'Clients'!A2"
    assert update["body"]["values"] == [["yes"]]
