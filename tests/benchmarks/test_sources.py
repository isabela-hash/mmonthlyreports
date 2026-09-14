from unittest.mock import MagicMock
import pytest
from tools.benchmarks.sources import action_value, meta, collect


def test_purchase_aliases_are_not_added_together():
    assert action_value([{"action_type": "purchase", "value": "4"}, {"action_type": "omni_purchase", "value": "4"}], "purchase") == 4
    assert action_value([], None) is None
    with pytest.raises(ValueError): action_value([{"action_type": "purchase", "value": "4"}] * 2, "purchase")


def test_meta_months_and_safe_pagination(monkeypatch):
    monkeypatch.setenv("META_ACCESS_TOKEN", "secret")
    monkeypatch.setenv("META_API_VERSION", "v25.0")
    account = {"source": "meta", "id": "123", "currency": "USD", "timezone": "America/New_York", "attribution": "7d click", "attribution_windows": ["7d_click"], "conversion_definition": "purchase event", "purchase_action": "purchase", "lead_action": "lead"}
    mock = MagicMock(side_effect=[{"currency": "USD", "timezone_name": "America/New_York"}, {"data": [{"country": "US", "spend": "100", "inline_link_clicks": "20", "actions": [{"action_type": "purchase", "value": "4"}], "action_values": [{"action_type": "purchase", "value": "300"}]}], "paging": {"next": "https://untrusted.invalid/?secret=token", "cursors": {"after": "cursor"}}}, {"data": []}])
    monkeypatch.setattr("tools.benchmarks.sources.request_json", mock)
    result = meta(account, ["2026-08"])
    assert len(result) == 1 and result[0]["sales"] == 4
    assert "graph.facebook.com" in mock.call_args.args[0] and "untrusted" not in mock.call_args.args[0]
    assert "secret" not in mock.call_args.args[0]


def test_source_failure_is_explicit_and_no_fake_rows(monkeypatch):
    account = {"source": "hyros", "id": "123", "mode": "export", "export_file_id": "private-id"}
    monkeypatch.setattr("tools.benchmarks.sources.read_json", MagicMock(side_effect=RuntimeError("private details")))
    result = collect({"clients": [{"code": "Client A", "accounts": [account]}]}, ["2026-08"], MagicMock())
    assert result["rows"] == []
    assert result["failures"][0]["reason"] == "Extraction or validation failed"
