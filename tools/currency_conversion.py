"""Deterministic source-currency conversion for monthly marketing reports."""
from __future__ import annotations

import json
import os
import csv
import io
from calendar import monthrange
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from tools.report_periods import month_name_to_number

BANXICO_SERIES_ID = "SF63528"
BANXICO_SERVICE_URL = "https://www.banxico.org.mx/SieAPIRest/service/v1"
BANXICO_PUBLIC_EXPORT_URL = (
    "https://www.banxico.org.mx/SieInternet/"
    "consultarDirectorioInternetAction.do?accion=consultarSeries"
)
BANXICO_POLICY = "banxico_monthly_average"
NO_FX_POLICY = "none"
MONETARY_COLUMNS = (
    "Cost",
    "Revenue",
    "Recurring Revenue",
    "Total Revenue",
    "Average Order Value",
)
MANUAL_MONEY_KEYS = (
    "company_revenue",
    "ad_revenue",
    "ad_cost",
)


@dataclass(frozen=True)
class FxConversion:
    source_currency: str
    report_currency: str
    policy: str
    period: str
    mxn_per_usd: float
    usd_per_mxn: float
    observation_count: int
    source: str = f"Banco de México SIE {BANXICO_SERIES_ID}"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_currency(value: str | None, default: str = "USD") -> str:
    normalized = str(value or default).strip().upper()
    if normalized not in {"USD", "MXN", "EUR"}:
        raise ValueError(f"Unsupported currency {value!r}. Expected USD, MXN, or EUR.")
    return normalized


def normalize_fx_policy(value: str | None) -> str:
    normalized = str(value or NO_FX_POLICY).strip().lower()
    if normalized not in {NO_FX_POLICY, BANXICO_POLICY}:
        raise ValueError(
            f"Unsupported FX policy {value!r}. Expected {NO_FX_POLICY!r} or {BANXICO_POLICY!r}."
        )
    return normalized


def _month_bounds(month: str, year: int) -> tuple[date, date]:
    month_number = month_name_to_number(month)
    start = date(year, month_number, 1)
    end = date(year, month_number, monthrange(year, month_number)[1])
    return start, end


def _fetch_banxico_json(url: str, token: str, timeout_seconds: int = 30) -> dict[str, Any]:
    request = Request(
        url,
        headers={"Bmx-Token": token, "Accept": "application/json"},
    )
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - fixed official HTTPS endpoint
        return json.loads(response.read().decode("utf-8"))


def _fetch_banxico_public_csv(year: int, timeout_seconds: int = 30) -> str:
    body = urlencode(
        {
            "idCuadro": "CF373",
            "sector": "6",
            "version": "3",
            "locale": "en",
            "series": BANXICO_SERIES_ID,
            "anoInicial": str(year),
            "anoFinal": str(year),
            "formatoHorizontal": "false",
            "formatoCSV.x": "1",
            "formatoCSV.y": "1",
        }
    ).encode("ascii")
    request = Request(
        BANXICO_PUBLIC_EXPORT_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - fixed official HTTPS endpoint
        return response.read().decode("latin-1")


def _rates_from_public_csv(csv_text: str, month_number: int, year: int) -> list[float]:
    rates: list[float] = []
    for row in csv.reader(io.StringIO(csv_text)):
        if len(row) != 2:
            continue
        try:
            observed = date.fromisoformat(
                f"{row[0][6:10]}-{row[0][0:2]}-{row[0][3:5]}"
            )
            rate = float(row[1].replace(",", ""))
        except (TypeError, ValueError, IndexError):
            continue
        if observed.year == year and observed.month == month_number:
            rates.append(rate)
    return rates


def fetch_banxico_monthly_average(
    month: str,
    year: int,
    token: str | None = None,
    fetch_json: Callable[[str, str], dict[str, Any]] | None = None,
    fetch_csv: Callable[[int], str] | None = None,
) -> FxConversion:
    """Return the arithmetic monthly average of Banco de México MXN-per-USD observations."""
    start, end = _month_bounds(month, int(year))
    resolved_token = (token or os.environ.get("BANXICO_API_TOKEN", "")).strip()
    source = f"Banco de México SIE {BANXICO_SERIES_ID} public CSV"
    if resolved_token or fetch_json:
        url = (
            f"{BANXICO_SERVICE_URL}/series/{BANXICO_SERIES_ID}/datos/"
            f"{start.isoformat()}/{end.isoformat()}"
        )
        payload = (fetch_json or _fetch_banxico_json)(url, resolved_token)
        series = payload.get("bmx", {}).get("series", [])
        observations = series[0].get("datos", []) if series else []
        rates = []
        for observation in observations:
            try:
                rates.append(float(str(observation.get("dato", "")).replace(",", "")))
            except (TypeError, ValueError):
                continue
        source = f"Banco de México SIE API {BANXICO_SERIES_ID}"
    else:
        rates = _rates_from_public_csv(
            (fetch_csv or _fetch_banxico_public_csv)(int(year)),
            start.month,
            int(year),
        )
    if not rates:
        raise ValueError(
            f"Banco de México returned no usable MXN-per-USD observations for {month} {year}."
        )
    average = sum(rates) / len(rates)
    if average <= 0:
        raise ValueError(f"Banco de México returned an invalid MXN-per-USD average for {month} {year}.")
    return FxConversion(
        source_currency="MXN",
        report_currency="USD",
        policy=BANXICO_POLICY,
        period=f"{month} {year}",
        mxn_per_usd=average,
        usd_per_mxn=1 / average,
        observation_count=len(rates),
        source=source,
    )


def resolve_fx_conversion(
    source_currency: str,
    report_currency: str,
    fx_policy: str,
    month: str,
    year: int,
    token: str | None = None,
    fetch_json: Callable[[str, str], dict[str, Any]] | None = None,
    fetch_csv: Callable[[int], str] | None = None,
) -> FxConversion | None:
    source = normalize_currency(source_currency)
    target = normalize_currency(report_currency)
    policy = normalize_fx_policy(fx_policy)
    if source == target:
        if policy != NO_FX_POLICY:
            raise ValueError("An FX policy is only valid when source_currency and report_currency differ.")
        return None
    if (source, target, policy) != ("MXN", "USD", BANXICO_POLICY):
        raise ValueError(
            "Only MXN to USD conversion using banxico_monthly_average is supported by this report pipeline."
        )
    return fetch_banxico_monthly_average(
        month,
        year,
        token=token,
        fetch_json=fetch_json,
        fetch_csv=fetch_csv,
    )


def convert_dataframe_monetary_values(df: pd.DataFrame, conversion: FxConversion | None) -> pd.DataFrame:
    """Return a report-only dataframe with money values converted; never changes the source Sheet."""
    converted = df.copy()
    if conversion is None:
        return converted
    for column in MONETARY_COLUMNS:
        if column in converted.columns:
            converted[column] = pd.to_numeric(converted[column], errors="coerce").fillna(0.0) * conversion.usd_per_mxn
    return converted


def convert_manual_money_values(values: dict[str, Any], conversion: FxConversion | None) -> dict[str, Any]:
    converted = dict(values)
    if conversion is None:
        return converted
    for key in MANUAL_MONEY_KEYS:
        if key not in converted:
            continue
        try:
            converted[key] = float(converted[key]) * conversion.usd_per_mxn
        except (TypeError, ValueError):
            continue
    return converted
