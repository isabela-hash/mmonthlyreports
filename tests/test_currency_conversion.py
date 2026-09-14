import pandas as pd
import pytest

from tools.currency_conversion import (
    BANXICO_POLICY,
    convert_dataframe_monetary_values,
    convert_manual_money_values,
    fetch_banxico_monthly_average,
    resolve_fx_conversion,
)
from tools.validate_data import canonicalize_traffic_sources, validate_or_raise
from tools import run_google_slides_report as runner


def _payload(*rates):
    return {"bmx": {"series": [{"datos": [{"dato": str(rate)} for rate in rates]}]}}


def test_banxico_monthly_average_uses_all_business_day_observations():
    conversion = fetch_banxico_monthly_average(
        "August",
        2026,
        token="test-token",
        fetch_json=lambda _url, _token: _payload("17.0", "18.0", "N/E"),
    )

    assert conversion.policy == BANXICO_POLICY
    assert conversion.mxn_per_usd == 17.5
    assert conversion.usd_per_mxn == pytest.approx(1 / 17.5)
    assert conversion.observation_count == 2


def test_mxn_to_usd_converts_all_report_money_fields_without_mutating_source():
    conversion = fetch_banxico_monthly_average(
        "August", 2026, token="test-token", fetch_json=lambda *_args: _payload("20")
    )
    source = pd.DataFrame(
        [{"Cost": 200, "Revenue": 400, "Recurring Revenue": 100, "Total Revenue": 500, "Average Order Value": 50}]
    )

    converted = convert_dataframe_monetary_values(source, conversion)

    assert source.loc[0, "Cost"] == 200
    assert converted.loc[0, "Cost"] == 10
    assert converted.loc[0, "Revenue"] == 20
    assert converted.loc[0, "Recurring Revenue"] == 5
    assert converted.loc[0, "Total Revenue"] == 25
    assert converted.loc[0, "Average Order Value"] == 2.5


def test_manual_money_values_use_the_matching_month_rate():
    conversion = fetch_banxico_monthly_average(
        "July", 2026, token="test-token", fetch_json=lambda *_args: _payload("25")
    )

    converted = convert_manual_money_values(
        {"company_revenue": 2500, "ad_revenue": 500, "ad_cost": 250}, conversion
    )

    assert converted == {"company_revenue": 100, "ad_revenue": 20, "ad_cost": 10}


def test_usd_client_skips_conversion_and_needs_no_banxico_token():
    assert resolve_fx_conversion("USD", "USD", "none", "August", 2026) is None


def test_legacy_eur_display_flag_keeps_eur_as_the_source_currency():
    args = runner.build_run_namespace(currency="EUR", report_currency="", source_currency="")

    assert runner._resolve_source_currency(args, "EUR") == "EUR"


def test_banxico_policy_uses_official_public_csv_without_secret(monkeypatch):
    monkeypatch.delenv("BANXICO_API_TOKEN", raising=False)
    csv_text = "Date,SF63528\n08/03/2026,17.0\n08/04/2026,18.0\n"

    conversion = resolve_fx_conversion(
        "MXN",
        "USD",
        BANXICO_POLICY,
        "August",
        2026,
        fetch_csv=lambda _year: csv_text,
    )

    assert conversion is not None
    assert conversion.mxn_per_usd == 17.5
    assert "public CSV" in conversion.source


def test_google_v2_is_valid_google_without_changing_source_dataframe():
    source = pd.DataFrame(
        [{"Traffic Source": "google v2", "Funnel": "TOF", "Cost": 10, "Total Revenue": 20, "Sales": 1, "Leads": 2, "Click": 3, "Impressions": 4, "Average Order Value": 20}]
    )

    canonical = canonicalize_traffic_sources(source)

    assert source.loc[0, "Traffic Source"] == "google v2"
    assert canonical.loc[0, "Traffic Source"] == "google"
    assert validate_or_raise(source)["checkpoint_1_passed"] is True
