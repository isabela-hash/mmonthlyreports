"""Pure calculations. No campaign-name geography or attribution mixing."""
from __future__ import annotations
import calendar
import hashlib
import json
import math
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

# UN M49 geographic regions, with requested reporting overrides.
# https://unstats.un.org/unsd/methodology/m49/
REGIONS = {
    "USA": "US",
    "UK + Canada": "GB CA",
    "Europe": "AX AL AD AT BY BE BA BG HR CZ DK EE FO FI FR DE GI GR GG VA HU IS IE IM IT JE LV LI LT LU MT MD MC ME NL MK NO PL PT RO RU SM RS SK SI ES SJ SE CH UA",
    "LATAM": "AI AG AR AW BS BB BZ BO BQ BV BR KY CL CO CR CU CW DM DO EC SV FK GF GD GP GT GY HT HN JM MQ MX MS NI PA PY PE PR BL KN LC MF VC SX GS SR TT TC UY VE VG VI",
    "India": "IN",
    "Asia": "AF AM AZ BH BD BT BN KH CN CX CC CY GE HK ID IR IQ IL JP JO KZ KP KR KW KG LA LB MO MY MV MN MM NP OM PK PS PH QA SA SG LK SY TW TJ TH TL TR TM UZ VN YE",
    "Africa": "IO DZ AO BJ BW BF BI CV CM CF TD KM CG CD CI DJ EG GQ ER SZ ET TF GA GM GH GN GW KE LS LR LY MG MW ML MR MU YT MA MZ NA NE NG RE RW SH ST SN SC SL SO ZA SS SD TZ TG TN UG EH ZM ZW",
    "UAE": "AE",
    "Other": "BM GL PM AS AQ AU CK FJ PF GU HM KI MH FM NR NC NZ NU NF MP PW PG PN WS SB TK TO TV UM VU WF",
}
COUNTRY_REGION = {country: region for region, codes in REGIONS.items() for country in codes.split()}
SOURCES = {"hyros", "meta", "google"}
FIELDS = ("spend", "clicks", "revenue", "sales", "leads")
RATIOS = {"cps": ("spend", "sales"), "cpc": ("spend", "clicks"), "aov": ("revenue", "sales"), "cpl": ("spend", "leads"), "roas": ("revenue", "spend")}
REPORT_ID = re.compile(r"^\d{4}-(0[1-9]|1[0-2])-r[1-9]\d{0,3}$")


def six_months(as_of: date) -> list[str]:
    month_index = as_of.year * 12 + as_of.month - 1
    return [f"{n // 12:04d}-{n % 12 + 1:02d}" for n in range(month_index - 6, month_index)]


def due(now: datetime) -> bool:
    local = now.astimezone(ZoneInfo("Europe/Madrid"))
    return local.day == 8 and local.hour == 9


def number(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("Boolean is not a metric")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError("Metrics must be finite and nonnegative")
    return result


def totals(rows: list[dict]) -> dict:
    # Do not divide a partial numerator by a complete denominator.
    return {field: sum(row[field] for row in rows) if rows and all(row.get(field) is not None for row in rows) else None for field in FIELDS}


def metrics(values: dict) -> dict:
    return {key: values[a] / values[b] if values.get(a) is not None and values.get(b) is not None and values[b] > 0 else None for key, (a, b) in RATIOS.items()}


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * p
    low, high = math.floor(index), math.ceil(index)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def benchmarks(rows: list[dict], clients: list[dict]) -> dict:
    eligible = {client["code"] for client in clients if client.get("prop_verified") is True}
    per_client = [metrics(totals([r for r in rows if r["client"] == code and r["country"] != "ZZ"])) for code in eligible]
    result = {}
    for key in RATIOS:
        values = [m[key] for m in per_client if m[key] is not None]
        result[key] = {"count": len(values), "median": percentile(values, .5) if len(values) >= 5 else None,
                       "q1": percentile(values, .25) if len(values) >= 5 else None, "q3": percentile(values, .75) if len(values) >= 5 else None}
    return result


def validate_config(config: dict):
    clients = config["clients"]
    codes = [c["code"] for c in clients]
    if not clients or len(codes) != len(set(codes)) or any(not re.fullmatch(r"Client [A-Z]{1,3}", c) for c in codes):
        raise ValueError("Unique stable client codes required")
    accounts = [(a["source"], a["id"]) for c in clients for a in c.get("accounts", [])]
    if len(accounts) != len(set(accounts)):
        raise ValueError("An account must belong to exactly one client")
    for client in clients:
        if not client.get("name"):
            raise ValueError("Private client name required")
        for account in client.get("accounts", []):
            if account["source"] not in SOURCES or not account["id"]:
                raise ValueError("Invalid source account")


def normalize(bundle: dict, config: dict, months: list[str]) -> list[dict]:
    """Accept account/country/month aggregates only; duplicates are rejected."""
    validate_config(config)
    owners = {(a["source"], a["id"]): c["code"] for c in config["clients"] for a in c.get("accounts", [])}
    output, seen = [], set()
    currency_by_account_month = {}
    for item in bundle["rows"]:
        source, account, month = item["source"], item["account_id"], item["month"]
        if (source, account) not in owners:
            raise ValueError("Unmapped source account")
        if month not in months:
            raise ValueError("Row outside requested six complete months")
        country = str(item.get("country") or "ZZ").upper()
        if country in ("-", "UNKNOWN", "UNASSIGNED"):
            country = "ZZ"
        if country != "ZZ" and country not in COUNTRY_REGION:
            raise ValueError("Country must be an ISO alpha-2 source field")
        if item.get("geo_basis") != "source_country":
            raise ValueError("Source-reported country required")
        for field in ("timezone", "attribution", "conversion_definition", "extracted_at", "currency", "source_ref"):
            if not item.get(field):
                raise ValueError(f"Missing provenance: {field}")
        ZoneInfo(item["timezone"])
        stamp = datetime.fromisoformat(item["extracted_at"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("Extraction timestamp must include timezone")
        year, month_number = map(int, month.split("-"))
        if stamp.astimezone(ZoneInfo(item["timezone"])).date() <= date(year, month_number, calendar.monthrange(year, month_number)[1]):
            raise ValueError("Export predates complete reporting month")
        key = (source, account, month, country)
        if key in seen:
            raise ValueError("Duplicate account/country/month; aggregate exports before import")
        seen.add(key)
        values = {field: number(item.get(field)) for field in FIELDS}
        if source == "hyros" and item.get("spend_compatible") is not True:
            values["spend"] = None
            values["clicks"] = None
        currency = item["currency"].upper()
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError("Invalid currency code")
        currency_key = (source, account, month)
        if currency_key in currency_by_account_month and currency_by_account_month[currency_key] != currency:
            raise ValueError("Inconsistent account currency within a month")
        currency_by_account_month[currency_key] = currency
        fx = None
        if currency != "USD":
            fx = bundle.get("fx", {}).get(f"{month}:{currency}")
            if not fx or not fx.get("source") or not fx.get("method") or not number(fx.get("usd_per_unit")):
                raise ValueError("Documented monthly USD exchange rate required")
            for field in ("spend", "revenue"):
                if values[field] is not None:
                    values[field] *= float(fx["usd_per_unit"])
        output.append({**values, "client": owners[(source, account)], "source": source, "month": month,
                       "country": country, "region": COUNTRY_REGION.get(country, "Unknown"),
                       "provenance": {k: item[k] for k in ("account_id", "timezone", "attribution", "conversion_definition", "extracted_at", "currency", "source_ref")},
                       "fx": fx})
    # Different attribution definitions/timezones must never silently share a total.
    for source in SOURCES:
        contracts = {(r["provenance"]["timezone"], r["provenance"]["attribution"], r["provenance"]["conversion_definition"]) for r in output if r["source"] == source}
        if len(contracts) > 1:
            raise ValueError(f"Incompatible measurement contracts within {source}; standardize the export definitions")
    return output


def snapshot(bundle: dict, config: dict, as_of: date, revision: int = 1) -> dict:
    if not 1 <= revision <= 9999:
        raise ValueError("Invalid revision")
    months = six_months(as_of)
    rows = normalize(bundle, config, months)
    if not rows:
        raise ValueError("No verified data; previous snapshot retained")
    fingerprint = hashlib.sha256(json.dumps({"rows": rows, "clients": config["clients"]}, sort_keys=True).encode()).hexdigest()
    return {"schema_version": 1, "id": f"{as_of:%Y-%m}-r{revision}", "months": months, "currency": "USD",
            "created_at": datetime.now(ZoneInfo("UTC")).isoformat(), "fingerprint": fingerprint,
            "clients": config["clients"], "rows": rows, "refresh": bundle.get("refresh", "dated_export"),
            "failures": bundle.get("failures", []), "industry_references": []}


def public_view(document: dict, private: bool = False) -> dict:
    """Explicit allowlist: never redact a private object by deleting known fields."""
    clients = []
    for c in document["clients"]:
        entry = {"code": c["code"], "prop_verified": c.get("prop_verified") is True}
        if private:
            entry["name"] = c["name"]
        clients.append(entry)
    rows = [{k: r[k] for k in (*FIELDS, "client", "source", "month", "country", "region")} for r in document["rows"]]
    result = {"schema_version": 1, "id": document["id"], "months": document["months"], "currency": "USD", "created_at": document["created_at"],
              "clients": clients, "rows": rows, "refresh": "api" if document.get("refresh") == "api" else "dated_export",
              "failed_sources": len(document.get("failures", [])), "industry_references": []}
    if private:
        result["provenance"] = [r["provenance"] | {"client": r["client"], "month": r["month"], "country": r["country"], "fx": r["fx"]} for r in document["rows"]]
        result["failures"] = document.get("failures", [])
    return result
