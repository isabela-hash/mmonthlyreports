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


def test_google_conversion_queries_do_not_duplicate_spend(monkeypatch):
    from types import SimpleNamespace
    for name in ["GOOGLE_ADS_REFRESH_TOKEN", "GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_DEVELOPER_TOKEN"]:
        monkeypatch.setenv(name, "fixture")
    monkeypatch.setenv("GOOGLE_ADS_API_VERSION", "v25")
    monkeypatch.setattr("google.oauth2.credentials.Credentials", lambda *a, **kw: SimpleNamespace(token="fixture", refresh=lambda request: None))
    def response(url, headers, body):
        sql = body["query"]
        if "FROM customer" in sql:
            result = [{"customer": {"currencyCode": "USD", "timeZone": "UTC"}}]
        elif "FROM geo_target_constant" in sql:
            result = [{"geoTargetConstant": {"id": "2840", "countryCode": "US"}}]
        elif "cost_micros" in sql:
            result = [{"userLocationView": {"countryCriterionId": "2840"}, "metrics": {"costMicros": "100000000", "clicks": "20"}}]
        else:
            result = [{"userLocationView": {"countryCriterionId": "2840"}, "segments": {"conversionAction": action}, "metrics": {"conversions": count, "conversionsValue": value}} for action, count, value in [("purchase", 4, 300), ("lead", 10, 0), ("duplicate-import", 4, 300)]]
        return [{"results": result}]
    monkeypatch.setattr("tools.benchmarks.sources.request_json", response)
    from tools.benchmarks.sources import google
    rows = google({"source": "google", "id": "123", "currency": "USD", "timezone": "UTC", "attribution": "test", "conversion_definition": "test", "purchase_actions": ["purchase"], "lead_actions": ["lead"], "purchase_value_verified": True}, ["2026-08"])
    assert len(rows) == 1
    assert rows[0]["spend"] == 100 and rows[0]["sales"] == 4 and rows[0]["revenue"] == 300 and rows[0]["leads"] == 10
