"""Read-only platform adapters and dated Drive export ingestion.

Each account uses one ingestion mode, preventing API/export double counting.
Conversion mappings are explicit; overlapping purchase event aliases are never summed.
"""
from __future__ import annotations
import calendar
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from tools.benchmarks.storage import read_json


def request_json(url, headers=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **(headers or {})})
    # No API URLs/tokens are included in raised user-visible errors.
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            return json.load(response)
    except Exception:
        raise RuntimeError("Source API request failed; check credentials, permissions and API version") from None


def bounds(month):
    year, number = map(int, month.split("-"))
    return month + "-01", f"{month}-{calendar.monthrange(year, number)[1]}"


def provenance(account):
    return {"source": account["source"], "account_id": account["id"], "geo_basis": "source_country",
            "currency": account["currency"], "timezone": account["timezone"], "attribution": account["attribution"],
            "conversion_definition": account["conversion_definition"], "extracted_at": datetime.now(timezone.utc).isoformat(),
            "source_ref": f"{account['source']} account {account['id']}"}


def action_value(actions, name):
    if not name:
        return None
    matches = [float(a["value"]) for a in actions or [] if a["action_type"] == name]
    if len(matches) > 1:
        raise ValueError("Duplicate conversion action")
    return matches[0] if matches else 0.0


def meta(account, months):
    token = os.environ[account.get("token_env", "META_ACCESS_TOKEN")]
    version = os.environ["META_API_VERSION"]
    if not re.fullmatch(r"v\d+\.0", version) or not account["id"].isdigit():
        raise ValueError("Invalid Meta account or version")
    headers = {"Authorization": f"Bearer {token}"}
    info = request_json(f"https://graph.facebook.com/{version}/act_{account['id']}?fields=currency,timezone_name", headers)
    if info["currency"] != account["currency"] or info["timezone_name"] != account["timezone"]:
        raise ValueError("Meta currency/timezone differs from approved configuration")
    output = []
    for month in months:
        start, end = bounds(month)
        params = {"fields": "country,spend,inline_link_clicks,actions,action_values,date_start,date_stop", "breakdowns": "country", "level": "account",
                  "time_range": json.dumps({"since": start, "until": end}), "action_attribution_windows": json.dumps(account["attribution_windows"]),
                  "action_report_time": "impression", "limit": "500"}
        while True:
            response = request_json(f"https://graph.facebook.com/{version}/act_{account['id']}/insights?" + urllib.parse.urlencode(params), headers)
            for row in response.get("data", []):
                output.append({**provenance(account), "month": month, "country": row["country"], "spend": row.get("spend"), "clicks": row.get("inline_link_clicks"),
                               "sales": action_value(row.get("actions"), account.get("purchase_action")),
                               "leads": action_value(row.get("actions"), account.get("lead_action")),
                               "revenue": action_value(row.get("action_values"), account.get("purchase_action")) if account.get("purchase_value_verified") is True else None})
            paging = response.get("paging", {})
            if not paging.get("next"):
                break
            # Rebuild the approved host URL instead of following token-bearing next URLs.
            params["after"] = paging["cursors"]["after"]
    return output


def google(account, months):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    creds = Credentials(None, refresh_token=os.environ["GOOGLE_ADS_REFRESH_TOKEN"], token_uri="https://oauth2.googleapis.com/token",
                        client_id=os.environ["GOOGLE_ADS_CLIENT_ID"], client_secret=os.environ["GOOGLE_ADS_CLIENT_SECRET"])
    creds.refresh(Request())
    version = os.environ["GOOGLE_ADS_API_VERSION"]
    if not re.fullmatch(r"v\d+", version) or not account["id"].isdigit():
        raise ValueError("Invalid Google account or version")
    headers = {"Authorization": f"Bearer {creds.token}", "developer-token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"]}
    if os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID"):
        headers["login-customer-id"] = os.environ["GOOGLE_ADS_LOGIN_CUSTOMER_ID"]
    endpoint = f"https://googleads.googleapis.com/{version}/customers/{account['id']}/googleAds:searchStream"
    def query(sql):
        return [row for page in request_json(endpoint, headers, {"query": sql}) for row in page.get("results", [])]
    customer = query("SELECT customer.currency_code, customer.time_zone FROM customer LIMIT 1")[0]["customer"]
    if customer["currencyCode"] != account["currency"] or customer["timeZone"] != account["timezone"]:
        raise ValueError("Google currency/timezone differs from approved configuration")
    locations = {str(row["geoTargetConstant"]["id"]): row["geoTargetConstant"]["countryCode"] for row in query("SELECT geo_target_constant.id, geo_target_constant.country_code FROM geo_target_constant WHERE geo_target_constant.target_type = 'Country'")}
    purchases, leads = account.get("purchase_actions", []), account.get("lead_actions", [])
    if set(purchases) & set(leads) or len(set(purchases)) != len(purchases) or len(set(leads)) != len(leads):
        raise ValueError("Overlapping Google conversion mappings")
    output = []
    for month in months:
        start, end = bounds(month)
        predicate = f"segments.date BETWEEN '{start}' AND '{end}'"
        rows = {}
        def country_row(item):
            criterion = str(item["userLocationView"]["countryCriterionId"])
            country = locations.get(criterion, "ZZ")
            if country not in rows:
                rows[country] = {**provenance(account), "country": country, "month": month, "spend": 0., "clicks": 0.,
                                 "sales": 0. if purchases else None, "revenue": 0. if purchases and account.get("purchase_value_verified") is True else None, "leads": 0. if leads else None}
            return rows[country]
        # Cost/clicks queried separately so conversion-action segmentation cannot duplicate spend.
        for item in query(f"SELECT user_location_view.country_criterion_id, metrics.cost_micros, metrics.clicks FROM user_location_view WHERE {predicate}"):
            row = country_row(item)
            row["spend"] += float(item["metrics"].get("costMicros", 0)) / 1_000_000
            row["clicks"] += float(item["metrics"].get("clicks", 0))
        for item in query(f"SELECT user_location_view.country_criterion_id, segments.conversion_action, metrics.conversions, metrics.conversions_value FROM user_location_view WHERE {predicate}"):
            row, action, values = country_row(item), item["segments"]["conversionAction"], item["metrics"]
            if action in purchases:
                row["sales"] += float(values.get("conversions", 0))
                if row["revenue"] is not None:
                    row["revenue"] += float(values.get("conversionsValue", 0))
            if action in leads:
                row["leads"] += float(values.get("conversions", 0))
        output.extend(rows.values())
    return output


def collect(config, months, drive):
    bundle = {"rows": [], "fx": config.get("fx", {}), "failures": [], "refresh": "api"}
    for client in config["clients"]:
        for account in client.get("accounts", []):
            try:
                mode = account.get("mode", "export")
                if mode == "export":
                    bundle["refresh"] = "dated_export"
                    exported = read_json(drive, account["export_file_id"])
                    rows = exported["rows"]
                    if any(r.get("account_id") != account["id"] or r.get("source") != account["source"] for r in rows):
                        raise ValueError("Export account mismatch")
                    rows = [r for r in rows if r.get("month") in months]
                elif mode == "api" and account["source"] in ("meta", "google"):
                    rows = {"meta": meta, "google": google}[account["source"]](account, months)
                else:
                    raise ValueError("Hyros requires a dated country export until its API geography is validated")
                # Validate each account independently; failed accounts cannot poison other clients.
                from tools.benchmarks.core import normalize
                normalize({"rows": rows, "fx": bundle["fx"]}, config, months)
                if not rows:
                    raise ValueError("No country data in this reporting window")
                bundle["rows"].extend(rows)
            except Exception:
                bundle["failures"].append({"client": client["code"], "source": account["source"], "account_id": account["id"], "reason": "Extraction or validation failed"})
    return bundle
