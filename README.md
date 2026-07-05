# ME Sales Panel (Streamlit)

Standalone dashboard + panel for the Middle East Sales Panel. Reads the same
BigQuery bridge the Google Sheets panel uses
(`css-operations.me_panel_dev_us.me_sales_panel_k_monthly`), so both surfaces
always show the same numbers. The bridge rebuilds every 12 hours.

## Tabs

- **Dashboard** - KPI cards (CWs, NRRA $, Gross RR $, Occupancy, Live Sold Rate)
  with month-over-month deltas, plus trend charts (RRA/RRL/NRRA, Gross RR vs
  RR after MKO/MFO, CWs vs Approved, Occupancy vs Live Sold Rates).
- **Panel** - the sheet-style table: metrics as rows, months as columns,
  per selected country (Middle East rollup + 5 countries).

## Run locally

```
cd me-panel-app
pip install -r requirements.txt        # or reuse an existing venv that has these
gcloud auth application-default login  # one-time, if not done already
streamlit run app.py
```

No secrets file is needed locally - the app uses your gcloud Application
Default Credentials.

## Deploy (Streamlit Cloud or a server)

1. Push this folder to a Git repo.
2. Add `.streamlit/secrets.toml` in the deployment with a `[gcp_service_account]`
   block (see `secrets.toml.example`). The service account needs BigQuery read
   access on `css-operations`.
3. Access control: set `ALLOWED_EMAILS` in the deployed secrets (see
   `secrets.toml.example`). No password - each allowed person just types
   their email once per session (same model as the kitchen tracker). With
   no `ALLOWED_EMAILS` configured the app is open (local use).

## Notes on the numbers

- Recognized revenue (RRA/RRL/NRRA $) matures over ~2 months; the live month
  shows deal-date figures until recognized loads, then switches automatically.
- Missing bridge columns are skipped silently, so appending columns to the
  bridge (the only allowed schema change) never breaks the app.
