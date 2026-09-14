# Google Slides Monthly Marketing Report — Workflow SOP

## Objective
Generate a branded monthly Google Slides report from the canonical Google Sheet, using Python for KPI validation/calculation and Google Slides API replacement for the final deck.

This workflow now supports both:
- a per-client runner for one sheet/template pair, and
- a master control sheet that orchestrates all active clients.

## Required Inputs
- `spreadsheet` — Google Sheet URL or ID containing Hyros report data.
- `template_presentation` — master Google Slides template URL or ID.
- `client` — exact Client column value.
- `month`, `year`, `prev_month`, `next_month`.
- Optional overrides: `company_revenue`, `ad_revenue`, `ad_cost`, `prev_company_revenue`, `prev_ad_revenue`, `prev_ad_cost`, media buyer notes, special requests.

## Runtime Contract
- Production target is a Cloud Run job, not an always-on service.
- Manual operator trigger target is a small Cloud Run service with a simple web page.
- Use Python `3.11+`.
- For Cloud Run, mount a service-account JSON and set `GOOGLE_SERVICE_ACCOUNT_FILE`.
- For local development, leave `GOOGLE_SERVICE_ACCOUNT_FILE` unset and rely on `credentials.json` plus cached OAuth tokens.
- `REPORT_INSIGHTS_PROVIDER` defaults to `auto` for real runs.
- `auto` tries Anthropic first, then OpenAI, and fails if neither API key is configured.
- `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` is required for test/production narrative generation.
- Set `GOOGLE_DRIVE_OUTPUT_FOLDER_ID` when the destination folder should come from environment defaults.
- Set `MASTER_CONTROL_SHEET_ID` for the multi-client batch runner.
- Set `CLOUD_RUN_PROJECT`, `CLOUD_RUN_REGION`, and `CLOUD_RUN_JOB_NAME` for the operator control panel.

## Required Google Sheet Tabs
- `Campaigns` — Hyros campaign rows. Custom tab names can be passed with `--campaigns-sheet`.
- `Ads` — Hyros ad rows. Custom tab names can be passed with `--ads-sheet`.

Optional for single-client/manual runs only:
- `Manual Inputs` — optional row-based or key/value inputs for company revenue, ad revenue, ad cost, notes, and requests.
- `KPI Output` — can be written by the per-client runner when you explicitly want it.
- `Run Log` — can be written by the per-client runner when you explicitly want it.

Each client should keep only its own data in its own Google Sheet. Do not store multi-client routing in the client sheets.

## Master Control Sheet
Use one separate control sheet for orchestration across the 14 clients.

- `Clients` tab:
  - Required columns: `active`, `client_name`, `client_key`, `spreadsheet_url_or_id`, `template_presentation_url_or_id`, `output_folder_id`
- Optional columns: `campaigns_tab`, `ads_tab`, `timezone`, `insights_provider`
- Optional currency columns: `source_currency` (defaults to `USD`), `report_currency` (defaults to `USD`), and `fx_policy` (defaults to `none`).
- For MXN source data displayed in USD, use `source_currency = MXN`, `report_currency = USD`, and `fx_policy = banxico_monthly_average`. The runner reads Banco de México's monthly average daily MXN-per-USD series and records the applied rate in the run log. `BANXICO_API_TOKEN` enables the API path; without it, the runner uses Banco de México's official public CSV export.
  - Use `insights_provider = auto` for active clients unless you are intentionally running a technical deterministic audit.
- `Runs` tab:
  - Centralized log for one row per client execution with provider used, deck URL, and error summary.

The batch runner defaults to centralized logging only, so client sheets can stay minimal with just `Campaigns` and `Ads`.

## Template Rules
- Use native Google Slides as the master template.
- Place `{{TOKEN}}` strings only in intentional text boxes or table cells.
- Never generate a template by globally replacing old numbers with tokens.
- Prefer complete-field tokens such as `{{GOOGLE_TOF_SALES}}`, `{{META_BOF_ROAS}}`, and full narrative tokens such as `{{GOOGLE_NEXT_STEPS}}`.
- Platform summary and total results use aggregate rows from the `Campaigns` tab.
- Funnel card placeholders such as `{{GOOGLE_TOF_REVENUE}}` use the highest-`Total Revenue` ad row for that platform/funnel from the `Ads` tab.
- Funnel card rows with zero `Total Revenue` are ignored; if no positive-revenue ad exists for that stage, the card shows `N/A`.
- The top ad rule is revenue-first. A lower-sales ad can win if it has the highest `Total Revenue`.
- `Company Revenue` and `% Of Revenue From Ads` are manual client-provided values for now; generated reports leave them at `$0.00` and `0%`.
- `% Of Revenue From Ads` stays `0%` until the technician enters client-provided company revenue manually.
- Use `workflows/template_placeholder_map.md` as the source of truth for template creation.

## Dry-Run Audit
Run this before generating a client deck:

```bash
python3 tools/run_google_slides_report.py \
  --template-presentation "GOOGLE_SLIDES_TEMPLATE_URL_OR_ID" \
  --client "One Funded" \
  --month March --year 2026 \
  --prev-month February --next-month April \
  --audit-only
```

The audit must show no `missing_values`. `unused_values` are okay; they mean the code can fill more tokens than this template currently uses.

## Generate a Deck
```bash
python3 tools/run_google_slides_report.py \
  --spreadsheet "GOOGLE_SHEET_URL_OR_ID" \
  --template-presentation "GOOGLE_SLIDES_TEMPLATE_URL_OR_ID" \
  --client "One Funded" \
  --month March --year 2026 \
  --prev-month February --next-month April \
  --company-revenue 93051 \
  --prev-company-revenue 68210 \
  --output-title "One Funded March 2026 Report - Automated" \
  --thumbnail-audit
```

By default this uses AI narratives through `auto`. Configure `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` before real runs.

## Run All Clients From The Control Sheet
```bash
python3 tools/run_control_sheet_reports.py \
  --control-sheet "MASTER_CONTROL_SHEET_URL_OR_ID" \
  --run-mode all \
  --month March --year 2026 \
  --insights-provider auto
```

To run one client only:

```bash
python3 tools/run_control_sheet_reports.py \
  --control-sheet "MASTER_CONTROL_SHEET_URL_OR_ID" \
  --run-mode one \
  --client-key "one-funded" \
  --month March --year 2026
```

## One Funded Test Command
```bash
python3 tools/run_google_slides_report.py \
  --spreadsheet "https://docs.google.com/spreadsheets/d/1QVOZAlPiD86t6qt32R-uS0cseQ6eeYn_m5WKoXrQ9B4/edit" \
  --template-presentation "https://docs.google.com/presentation/d/1sDL6pLcf-KrFDFu7F-vVLvdGr8azo55RGxEGEs1sCiU/edit" \
  --client "One Funded" \
  --month March --year 2026 \
  --prev-month February --next-month April \
  --campaigns-sheet "Campaigns OneFunded" \
  --ads-sheet "Ads OneFunded" \
  --company-revenue 93051 \
  --prev-company-revenue 68210 \
  --output-title "One Funded March 2026 Report - Dry Run" \
  --thumbnail-audit
```

This reads March as the current month and February as the previous month from the same spreadsheet, then fills both current and `_PREV` placeholders.

## Production Runner
Use the same image for both Cloud Run surfaces:

- Cloud Run Job:
  - Runs `tools/run_control_sheet_reports.py`
  - Handles `run all` or `run one`
  - Reads master control sheet config
- Cloud Run Service:
  - Runs `tools/report_ops_service.py`
  - Shows a simple internal web page for `Run all clients` and `Run one client`
  - Launches the Cloud Run Job asynchronously through the Cloud Run Admin API

Share the client Sheets, Slides templates, control sheet, and Drive output folders with the service account used by these workloads.

## MT Ops Portal

The internal portal is the technician-facing entrypoint for full report ops:

- Dashboard: lists active and inactive clients with latest report links.
- Client creation: creates the Drive folder, 2026 data Sheet, and master control row.
- Activation: safely toggles clients between staged/inactive and active.
- Preflight: checks current data, previous-period data, template audit, and latest report status.
- Runs: queues one client, all active clients, or only missing reports through the Cloud Run Job.

Supported run flags:

```bash
python3 tools/run_control_sheet_reports.py \
  --run-mode missing \
  --month May --year 2026 \
  --allow-first-month-baseline \
  --include-inactive
```

Use `--allow-first-month-baseline` only when the uploaded current-month data is complete but the client has no prior-month rows yet. The run is logged with a zero previous-period KPI baseline.

Phase rollout:
- Phase 1: use the Cloud Run service manually from the web page.
- Phase 2: once the first full monthly run succeeds, add Cloud Scheduler to trigger the same backend on the first day of each month.

## Release Gate
- GitHub Actions must pass tests, script compilation, and `run_google_slides_report.py --help`.
- `run_control_sheet_reports.py --help` must also pass.
- The Docker image must build successfully from the repo root.
- Run `--audit-only` against the real template before generating a client deck.
- Do not ship a template that reports `missing_values`.
- For current-month tests such as April, do not generate a deck until both `Campaigns` and `Ads` contain rows for the requested client/month/year.
