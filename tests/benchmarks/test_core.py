from datetime import date, datetime, timezone
import json
import pytest
from tools.benchmarks.core import normalize, snapshot, public_view, six_months, metrics, totals, benchmarks, COUNTRY_REGION, due


def config():
    return {"clients": [{"code": "Client A", "name": "Confidential Example", "prop_verified": True, "accounts": [{"source": "hyros", "id": "secret-account"}]}]}


def row(**overrides):
    return {"source": "hyros", "account_id": "secret-account", "month": "2026-08", "country": "US", "geo_basis": "source_country", "currency": "USD", "timezone": "America/New_York", "attribution": "Last click", "conversion_definition": "deduplicated purchases", "extracted_at": "2026-09-05T00:00:00Z", "source_ref": "private-source-link", "spend_compatible": True, "spend": 100, "sales": 4, "clicks": 20, "revenue": 300, "leads": 10, **overrides}


def test_calendar_and_dst():
    assert six_months(date(2026, 9, 14)) == [f"2026-{m:02}" for m in range(3, 9)]
    assert six_months(date(2026, 1, 8)) == [f"2025-{m:02}" for m in range(7, 13)]
    assert due(datetime(2026, 10, 8, 7, tzinfo=timezone.utc))
    assert due(datetime(2026, 11, 8, 8, tzinfo=timezone.utc))
    assert not due(datetime(2026, 11, 8, 7, tzinfo=timezone.utc))


def test_ratios_and_missing_denominators():
    assert metrics(totals([row()])) == {"cps": 25, "cpc": 5, "aov": 75, "cpl": 10, "roas": 3}
    assert metrics(totals([row(), row(spend=900, sales=6)]))["cps"] == 100
    assert metrics(totals([row(sales=0)]))["cps"] is None
    assert metrics(totals([row(), row(spend=None)]))["roas"] is None
    assert metrics(totals([]))["aov"] is None


def test_hyros_spend_must_be_compatible():
    normalized = normalize({"rows": [row(spend_compatible=False)]}, config(), ["2026-08"])[0]
    assert normalized["spend"] is None
    assert metrics(normalized)["aov"] == 75


@pytest.mark.parametrize("change", [{"spend": -1}, {"spend": float("nan")}, {"sales": True}, {"geo_basis": "campaign_name"}, {"country": "USA"}, {"account_id": "unmapped"}, {"extracted_at": "2026-08-01T00:00:00Z"}, {"currency": "EUR"}])
def test_invalid_data_fails(change):
    with pytest.raises(ValueError): normalize({"rows": [row(**change)]}, config(), ["2026-08"])


def test_duplicates_and_incompatible_contracts():
    with pytest.raises(ValueError, match="Duplicate"): normalize({"rows": [row(), row()]}, config(), ["2026-08"])
    with pytest.raises(ValueError, match="Incompatible"): normalize({"rows": [row(), row(country="CA", attribution="Other")]}, config(), ["2026-08"])
    bad = config(); bad["clients"].append({**bad["clients"][0], "code": "Client B"})
    with pytest.raises(ValueError, match="exactly one"): normalize({"rows": [row()]}, bad, ["2026-08"])


def test_fx_and_regions():
    bundle = {"rows": [row(currency="EUR")], "fx": {"2026-08:EUR": {"usd_per_unit": 1.2, "source": "central bank", "method": "monthly mean"}}}
    data = normalize(bundle, config(), ["2026-08"])[0]
    assert data["spend"] == 120 and data["revenue"] == 360
    assert COUNTRY_REGION["GB"] == COUNTRY_REGION["CA"] == "UK + Canada"
    assert COUNTRY_REGION["AE"] == "UAE" and COUNTRY_REGION["IN"] == "India"
    assert COUNTRY_REGION["DE"] == "Europe" and COUNTRY_REGION["MX"] == "LATAM"


def test_partial_history_and_share_allowlist():
    doc = snapshot({"rows": [row(country="-"), row(country="US")]}, config(), date(2026, 9, 14))
    shared = public_view(doc)
    text = json.dumps(shared)
    for private in ["Confidential Example", "secret-account", "private-source-link", "provenance", "accounts"]:
        assert private not in text
    assert shared["rows"][0]["country"] == "ZZ"
    assert len(shared["months"]) == 6
    assert "name" in public_view(doc, True)["clients"][0]
    with pytest.raises(ValueError, match="No verified data"): snapshot({"rows": []}, config(), date(2026, 9, 14))


def test_minimum_five_client_benchmark_and_unknown_exclusion():
    clients = [{"code": f"Client {letter}", "prop_verified": True} for letter in "ABCDE"]
    rows = [{**row(), "client": c["code"], "spend": (i + 1) * 100} for i, c in enumerate(clients)]
    band = benchmarks(rows, clients)["cps"]
    assert band == {"count": 5, "median": 75, "q1": 50, "q3": 100}
    assert benchmarks(rows[:-1], clients)["cps"]["median"] is None
    rows[-1]["country"] = "ZZ"
    assert benchmarks(rows, clients)["cps"]["count"] == 4


def test_currency_cannot_change_within_account_month():
    bundle = {"rows": [row(), row(country="CA", currency="EUR")], "fx": {"2026-08:EUR": {"usd_per_unit": 1.1, "source": "central bank", "method": "monthly mean"}}}
    with pytest.raises(ValueError, match="Inconsistent account currency"):
        normalize(bundle, config(), ["2026-08"])
