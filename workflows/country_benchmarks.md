# Country benchmark report operations

The report has separate Hyros, Meta and Google attribution views. It never derives geography from campaign names. Missing or incompatible data is unavailable. No real performance snapshot or live schedule is included in the source repository.

## Private configuration and source onboarding

Use `data/benchmarks/config.json` locally (gitignored); production reads `BENCHMARK_CONFIG_DRIVE_ID`. The local setup contains the requested 12 distinct clients with stable codes and the observed Meta account IDs. The duplicated client alias is one entry. Complete and verify each mapping before the first published run. Do not renumber codes when client order changes. Mark `prop_verified: true` only after verifying the client's business type. Unverified/software/financing clients remain visible and excluded from prop benchmark ranges.

Configuration shape (illustrative names/IDs only):

```json
{
  "folder_id": "PRIVATE_DRIVE_FOLDER_ID",
  "slots": {},
  "clients": [{
    "code": "Client A", "name": "Private company name", "prop_verified": false,
    "accounts": [{"source": "hyros", "id": "ACCOUNT_ID", "mode": "export", "export_file_id": "DATED_JSON_FILE_ID"}]
  }],
  "fx": {"2026-08:EUR": {"usd_per_unit": 1.1, "source": "CENTRAL_BANK_REFERENCE", "method": "monthly arithmetic mean"}}
}
```

Each account belongs to exactly one client and uses exactly one ingestion mode. Multiple accounts per client are supported. The example FX rate is illustrative, not a production rate. Monetary rates must be documented for every applicable currency/month. Do not substitute another month's rate. Non-USD rows without a valid rate fail validation.

### Dated exports (Hyros and fallback for platforms)

Export each complete month using the source's country field. Exclude totals/subtotals. Normalize country names to ISO alpha-2 codes using an explicit checked mapping, not campaign names. Aggregate to **source + account + month + country**; do not export both campaign aggregates and account aggregates. Do not combine different attribution models, conversion definitions or timezones within one source view.

A JSON export is `{"rows": [...]}`. CSV is also accepted by `--input` for local imports. Every row has:

- `source`: `hyros`, `meta`, or `google`; `account_id`, `month` (`YYYY-MM`), `country` (ISO alpha-2 or `ZZ` for unknown).
- `geo_basis`: exactly `source_country`.
- `currency`, IANA `timezone`, `attribution`, `conversion_definition`, timezone-aware `extracted_at`, private `source_ref`.
- `spend`, `clicks`, `revenue`, `sales`, `leads`: nonnegative numbers or null/blank. Fractional attributed conversions are allowed. Do not turn tracking omissions into zero.
- Hyros `spend_compatible`: true only when spend and conversion geography, channel scope, dates and attribution definitions have been reconciled. Otherwise spend/clicks are unavailable; revenue/sales/leads can still be reported.

Compare country sums, **including unknown**, to source account totals for each month before importing. A dated export must cover only complete months and record when it was pulled. Hyros's existing undated geo database and exports containing only `-` geography do not establish country benchmark coverage.

Keep these files in the same private Drive location. Updating an export file changes the next run's input; it never changes an archived snapshot. No API credentials belong in export rows or source links.

### Read-only platform APIs

Meta `mode: api` uses account Insights, country breakdown, impression-time reporting and `inline_link_clicks`. Configure `currency`, `timezone`, `attribution`, `conversion_definition`, `attribution_windows`, one `purchase_action` and one `lead_action`. Set `META_API_VERSION` and `META_ACCESS_TOKEN` (read-only `ads_read` access). Do not sum aliases such as purchase plus omni_purchase. The adapter checks account currency/timezone and follows pagination without following token-bearing URLs.

Google `mode: api` uses physical `user_location_view`, not location-of-interest matching. Configure `currency`, `timezone`, `attribution`, `conversion_definition`, `purchase_actions` and `lead_actions` as exact conversion-action resource names. Use disjoint, deduplicated conversion actions. Spend/clicks are queried separately from conversion-action segmentation to avoid multiplying spend. Configure all `GOOGLE_ADS_*` variables in `.env.example`, using an approved API version and read-only authorized account access.

Both platform adapters require `purchase_value_verified: true` before exposing purchase revenue; otherwise AOV/ROAS are unavailable. Verify event values and currency before enabling it.

Live platform adapters require reconciliation against matching source reports before production activation. Hyros uses dated exports until an available API response with equivalent geography, date and attribution coverage is validated; no unsupported Hyros endpoint is assumed.

## Audit, provision and publish

1. Install dependencies and set Google service-account credentials. Share an existing private Drive folder with that service account. Provisioning rejects public/domain-wide folders and never changes sharing.
2. Reserve atomic snapshot IDs and install private configuration:

```bash
.venv/bin/python tools/provision_country_benchmarks.py --config data/benchmarks/config.json --start 2026-09 --months 24 --revisions 3
```

Keep the returned config ID in `BENCHMARK_CONFIG_DRIVE_ID` on both the web app and Cloud Run. For later reservations, pass `--config-drive-id` with the same ID and the current private config containing existing slots. Never replace assigned slots. Extend reservations before the horizon expires.

3. Audit source data without publishing:

```bash
BENCHMARK_CONFIG_FILE=data/benchmarks/config.json .venv/bin/python tools/run_country_benchmarks.py --as-of 2026-09-08 --input data/benchmarks/export.json --audit-only
```

CSV imports accept `--metadata data/benchmarks/metadata.json` for the FX dictionary. The initial window is March–August 2026. Omitting `--as-of` calculates the previous six complete months from today's Madrid date.

4. Set independent random secrets of at least 32 characters for `BENCHMARK_PASSWORD_SEED` and `BENCHMARK_SESSION_SECRET`. Keep the seed stable and backed up: it derives distinct passphrases for every report and audience. Snapshot files store salted scrypt password hashes only. The web app needs the same seed to show report passwords to an authenticated portal operator.
5. Run without `--audit-only` to publish the snapshot. Optional `--password-output` writes passwords to a new local file with mode 0600; otherwise no password is printed. Operators can reveal passwords from the portal archive. Root seed changes must be coordinated; old passwords/hashes remain valid but cannot be re-derived with a different seed.

Reports are `/benchmarks/YYYY-MM-rN/private` and `/benchmarks/YYYY-MM-rN/share`. The archive requires portal authentication. Private-report passwords and share passwords are report/revision scoped; a share password cannot reveal the private view or password-management endpoint. The private portal login can open named reports. All report APIs use no-store. The shared response allowlist excludes names, account IDs, source links, hashes and private metadata; filtered CSV uses only that response.

A preallocated Drive file ID is created once. Concurrent retries cannot create duplicate copies. An existing monthly report is returned without re-extraction. Use `--revision 2` for corrected data; the previous copy is never edited. Partial extraction records failed sources and available client months. A run with no verified rows records a failed run and leaves existing copies intact. Cloud Run failure status provides operational monitoring.

## Hosted monthly job

The supplied `tools/setup_country_benchmark_schedule.sh` deploys a dedicated Cloud Run Job using the existing Dockerfile and an existing service account, then creates/updates one named Cloud Scheduler job for **09:00 on the 8th, Europe/Madrid**. It does not use a desktop automation.

Set the variables required at the top of the script, provide an already-built image and existing Secret Manager names, and ensure the scheduler identity already has `roles/run.invoker` for this job. Set optional `BENCHMARK_PLATFORM_SECRETS` to comma-separated environment-to-secret bindings for API mode. Configure API versions on the job as well. Running this script changes cloud resources; it has not been run in the local implementation.

The web application remains on its existing Next.js hosting. Its build needs the Python packages and Python runtime used by the current portal. Bundle tracing excludes local datasets, credentials and test fixtures. Configure the new secrets and private Drive ID in the correct hosting project; do not publish the private config via Git or a static public directory.

## Validation

- `npm run lint`, `npm run test:web`, `npx tsc --noEmit`, `npx next build`, `python tools/check_benchmark_bundle.py`.
- `.venv/bin/python -m pytest -q` and `.venv/bin/python -m py_compile tools/*.py tools/benchmarks/*.py`.
- `bash -n tools/setup_country_benchmark_schedule.sh` and repository Docker build gate.
- Browser: login, separate source tabs, country search, region drilldown, month filter, client comparison and CSV. Inspect shared HTML/JSON/downloads for identities; verify cross-report and cross-audience access is rejected.
- Before live rollout, reconcile representative account/country/month metrics to Hyros, Meta and Google independently and inspect conversion settings. Confirm the hosted schedule's timezone and next run. Browser login alone does not configure unattended API access.

Industry references remain explicitly unavailable until a source's methodology, population, dates and metric definitions support the comparison. No promotional industry ranges or challenge list prices are treated as observed AOV/ROAS benchmarks.
