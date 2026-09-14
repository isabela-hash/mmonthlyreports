# Master Control Sheet

- Title: `Monthly Report Master Control Sheet`
- Spreadsheet ID: `1Onwnphg3kdXp6YWTq5UHJQBWsuCNGjnw57SPrIFVVVQ`
- URL: `https://docs.google.com/spreadsheets/d/1Onwnphg3kdXp6YWTq5UHJQBWsuCNGjnw57SPrIFVVVQ/edit?usp=drivesdk`

Tabs created:

- `Clients`
- `Runs`

`Clients` headers:

- `active`
- `client_name`
- `client_key`
- `spreadsheet_url_or_id`
- `template_presentation_url_or_id`
- `output_folder_id`
- `campaigns_tab`
- `ads_tab`
- `timezone`
- `insights_provider`
- `source_currency` (optional; defaults to `USD`)
- `report_currency` (optional; defaults to `USD`)
- `fx_policy` (optional; defaults to `none`; FM Hub uses `banxico_monthly_average`)

Use `auto` for active clients so real runs use Anthropic/OpenAI narratives and fail clearly if no AI key is configured. Use `deterministic` only for explicit technical dry runs.

`Runs` headers:

- `timestamp_utc`
- `batch_run_id`
- `run_mode`
- `client_key`
- `client_name`
- `period`
- `status`
- `spreadsheet_id`
- `presentation_url`
- `requested_insights_provider`
- `used_insights_provider`
- `error_summary`
- `validation_json`

Currency conversion metadata is stored inside `validation_json`, including the monthly
MXN-per-USD average, reciprocal conversion rate, Banco de México series, and observation count.
