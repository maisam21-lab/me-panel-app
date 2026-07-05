"""ME Sales Panel - standalone Streamlit app.

Reads the BigQuery bridge table that also feeds the Google Sheets panel
(css-operations.me_panel_dev_us.me_sales_panel_k_monthly), so both surfaces
always show the same numbers. Two tabs: Dashboard (KPIs + trends) and
Panel (sheet-style metrics x months table).

Run locally:
    streamlit run app.py

Credentials (first match wins):
    1. [gcp_service_account] block in .streamlit/secrets.toml
    2. Application Default Credentials (gcloud auth application-default login)
"""
import math
from decimal import Decimal

import pandas as pd
import streamlit as st

BQ_PROJECT = "css-operations"
BRIDGE_TABLE = "css-operations.me_panel_dev_us.me_sales_panel_k_monthly"
COUNTRIES = ["Middle East", "Saudi Arabia", "UAE", "Kuwait", "Bahrain", "Qatar"]
START_MONTH = "2025-01-31"

st.set_page_config(page_title="ME Sales Panel", layout="wide", page_icon=":bar_chart:")

st.markdown(
    """
    <style>
    .stApp { background: #FAFBFC; }
    h1 { background: #0F766E; color: white !important; font-weight: 700;
         padding: 14px 24px; margin: 0 0 1rem 0; border-radius: 0 10px 10px 0; font-size: 1.3rem !important; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; background: #F1F5F9; padding: 8px; border-radius: 10px; }
    .stTabs [data-baseweb="tab"] { padding: 10px 18px; border-radius: 8px; font-weight: 600; color: #475569; }
    .stTabs [aria-selected="true"] { background: #0F766E !important; color: white !important; }
    .stTabs [aria-selected="true"] p { color: white !important; }
    [data-testid="stMetric"] { background: white; border: 1px solid #E2E8F0; border-radius: 10px;
        padding: 12px 16px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
    .stDataFrame thead th { background: #F1F5F9 !important; font-weight: 600 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _bq_client():
    from google.cloud import bigquery

    try:
        info = dict(st.secrets.get("gcp_service_account", {}))
    except Exception:
        info = {}
    if info and info.get("private_key"):
        try:
            from google.oauth2 import service_account

            info.setdefault("token_uri", "https://oauth2.googleapis.com/token")
            info.setdefault("auth_uri", "https://accounts.google.com/o/oauth2/auth")
            creds = service_account.Credentials.from_service_account_info(
                info, scopes=["https://www.googleapis.com/auth/bigquery.readonly"]
            )
            return bigquery.Client(project=BQ_PROJECT, credentials=creds)
        except Exception:
            pass  # invalid/placeholder SA -> fall through to ADC
    return bigquery.Client(project=BQ_PROJECT)  # Application Default Credentials


@st.cache_data(ttl=900, show_spinner="Loading panel data from BigQuery...")
def load_bridge() -> pd.DataFrame:
    """Pull the bridge (one row per country x month). Cached 15 min; the table rebuilds every 12h."""
    client = _bq_client()
    query = (
        "SELECT * FROM `" + BRIDGE_TABLE + "` "
        "WHERE month_end >= DATE '" + START_MONTH + "' "
        "AND month_end <= LAST_DAY(CURRENT_DATE(), MONTH) "
        "ORDER BY month_end, country"
    )
    rows = list(client.query(query).result())
    out = []
    for row in rows:
        d = dict(row)
        for k, v in list(d.items()):
            if isinstance(v, Decimal):
                d[k] = float(v)
        out.append(d)
    df = pd.DataFrame(out)
    if not df.empty:
        df["month_end"] = pd.to_datetime(df["month_end"])
    return df


def fmt(v, kind):
    """Panel-style display formatting. Empty string for missing values."""
    try:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return ""
        if kind == "usd":
            return f"${float(v):,.0f}"
        if kind == "usd2":
            return f"${float(v):,.2f}"
        if kind == "pct":
            return f"{float(v) * 100:.1f}%"
        if kind == "num1":
            return f"{float(v):,.1f}"
        return f"{float(v):,.0f}"
    except Exception:
        return "" if v is None else str(v)


# (label, bridge column, format). Section headers have col=None. Missing columns are
# skipped, so bridge schema APPENDS (the only allowed change there) never break the app.
METRICS = [
    ("Sales", None, None),
    ("CWs (kitchens)", "cws", "num"),
    ("Approved Deals", "approved_deals", "num"),
    ("Avg CW Duration (months)", "cw_duration", "num1"),
    ("New Occupied Kitchens", "new_occupied_k", "num"),
    ("Revenue $", None, None),
    ("RRA $ (recognized, CW-date)", "rra_usd", "usd"),
    ("RRL $ (recognized)", "rrl_usd", "usd"),
    ("NRRA $ (net)", "nrra_usd", "usd"),
    ("RRX $ (accessed)", "xrra_usd", "usd"),
    ("RRLX $ (post-access lost)", "xrrl_usd", "usd"),
    ("NRRX $ (net accessed)", "nrrx_usd", "usd"),
    ("Gross Recurring Revenue $ (EoP)", "gross_rr_usd", "usd"),
    ("RR after MKO/MFO $ (EoP)", "rr_after_mko_mfo_usd", "usd2"),
    ("TCV $", "tcv_usd", "usd"),
    ("Approved TCV $", "approved_tcv_usd", "usd"),
    ("Churn & Net", None, None),
    ("Churns (excl. transfers)", "churns_excl_transfers", "num"),
    ("Net Adds", "net_adds", "num"),
    ("Occupancy & Sold Rates", None, None),
    ("Occupancy", "occupancy", "pct"),
    ("Occupied Kitchens", "occupied_kitchens", "num"),
    ("Total Kitchen Numbers (TKN)", "total_kitchens", "num"),
    ("Live - Sold Rate %", "live_sold_rate", "pct"),
    ("Live - Sold Rate w/ Approved %", "live_sold_rate_approved", "pct"),
    ("Vacant w/ Approved Opp", "live_vacant_appr_k", "num"),
    ("Sold Rate - All Facilities", "sold_rate_all", "pct"),
    ("Sold Rate w/ Approved - All", "net_sold_approved_rate", "pct"),
    ("Team", None, None),
    ("Sales Team Size (FTE)", "sales_team_size", "num1"),
    ("AEs", "aes", "num1"),
    ("SDRs", "sdrs", "num1"),
]


def _allowed_emails() -> set:
    """ALLOWED_EMAILS from secrets: a TOML list or a comma/semicolon-separated string.
    Empty/absent = gate OFF (open app, e.g. local use)."""
    try:
        raw = st.secrets.get("ALLOWED_EMAILS", [])
    except Exception:
        return set()
    if isinstance(raw, str):
        raw = raw.replace(";", ",").split(",")
    return {str(e).strip().lower() for e in raw if str(e).strip()}


def _access_gate():
    """Lightweight allowlist gate (identification, not authentication - no password,
    same model as the kitchen tracker): user enters their email once per session."""
    allowed = _allowed_emails()
    if not allowed:
        return  # no allowlist configured -> open
    current = (st.session_state.get("me_user_email") or "").strip().lower()
    if current in allowed:
        return
    st.markdown("<h1>ME Sales Panel</h1>", unsafe_allow_html=True)
    st.write("Enter your work email to open the panel.")
    email = st.text_input("Email", key="me_email_input")
    if st.button("Open", type="primary"):
        if email.strip().lower() in allowed:
            st.session_state["me_user_email"] = email.strip()
            st.rerun()
        else:
            st.error("This email is not on the allowed list. Ask Maysam to add you.")
    st.stop()


def main():
    _access_gate()
    st.markdown("<h1>ME Sales Panel</h1>", unsafe_allow_html=True)

    try:
        df = load_bridge()
    except Exception as e:
        st.error(
            "Could not load the bridge from BigQuery. "
            "Check credentials ([gcp_service_account] in secrets, or run "
            "`gcloud auth application-default login`).\n\nDetails: " + str(e)
        )
        st.stop()
    if df.empty:
        st.warning("The bridge returned no rows.")
        st.stop()

    with st.sidebar:
        st.subheader("Filters")
        countries = [c for c in COUNTRIES if c in set(df["country"])]
        sel_country = st.selectbox("Country", countries, index=0)
        if st.button("Refresh data"):
            load_bridge.clear()
            st.rerun()
        st.caption(
            "Source: `" + BRIDGE_TABLE + "` - rebuilt every 12h. "
            "Same bridge the Google Sheets panel reads, so both always match. "
            "Recognized revenue months mature over ~2 months; the live month "
            "shows deal-date figures until recognized loads."
        )

    d = df[df["country"] == sel_country].sort_values("month_end").reset_index(drop=True)
    if d.empty:
        st.info("No rows for this country.")
        st.stop()
    d["month_label"] = d["month_end"].dt.strftime("%b %Y")

    tab_dash, tab_panel = st.tabs(["Dashboard", "Panel"])

    # ---------------- Dashboard tab ----------------
    with tab_dash:
        last = d.iloc[-1]
        prev = d.iloc[-2] if len(d) > 1 else None

        def delta(col):
            try:
                if prev is None or col not in d.columns:
                    return None
                return float(last[col]) - float(prev[col])
            except Exception:
                return None

        k1, k2, k3, k4, k5 = st.columns(5)
        with k1:
            dv = delta("cws")
            st.metric("CWs - " + str(last["month_label"]), fmt(last.get("cws"), "num"),
                      delta=(fmt(dv, "num") if dv is not None else None))
        with k2:
            dv = delta("nrra_usd")
            st.metric("NRRA $", fmt(last.get("nrra_usd"), "usd"),
                      delta=(fmt(dv, "usd") if dv is not None else None))
        with k3:
            dv = delta("gross_rr_usd")
            st.metric("Gross RR $ (EoP)", fmt(last.get("gross_rr_usd"), "usd"),
                      delta=(fmt(dv, "usd") if dv is not None else None))
        with k4:
            dv = delta("occupancy")
            st.metric("Occupancy", fmt(last.get("occupancy"), "pct"),
                      delta=(f"{dv * 100:+.1f} pp" if dv is not None else None))
        with k5:
            dv = delta("live_sold_rate")
            st.metric("Live Sold Rate", fmt(last.get("live_sold_rate"), "pct"),
                      delta=(f"{dv * 100:+.1f} pp" if dv is not None else None))

        try:
            import plotly.graph_objects as go
            has_plotly = True
        except ImportError:
            has_plotly = False
            st.info("plotly not installed - charts unavailable (pip install plotly).")

        if has_plotly:
            x = d["month_label"].tolist()

            def line_fig(series, title, is_pct=False):
                fig = go.Figure()
                for lbl, col, color in series:
                    if col in d.columns:
                        fig.add_trace(go.Scatter(x=x, y=d[col], mode="lines+markers", name=lbl,
                                                 line=dict(color=color, width=2)))
                fig.update_layout(title=title, height=340, margin=dict(l=10, r=10, t=45, b=10),
                                  legend=dict(orientation="h", y=-0.25), plot_bgcolor="white")
                if is_pct:
                    fig.update_yaxes(tickformat=".0%")
                return fig

            c1, c2 = st.columns(2)
            with c1:
                st.plotly_chart(line_fig(
                    [("RRA $", "rra_usd", "#0F766E"), ("RRL $", "rrl_usd", "#DC2626"),
                     ("NRRA $", "nrra_usd", "#2563EB")],
                    "Recurring Revenue (recognized) - added / lost / net"), use_container_width=True)
            with c2:
                st.plotly_chart(line_fig(
                    [("Gross RR $", "gross_rr_usd", "#0F766E"),
                     ("RR after MKO/MFO $", "rr_after_mko_mfo_usd", "#7C3AED")],
                    "Occupied-kitchen revenue at End of Period (gap = concession load)"),
                    use_container_width=True)
            c3, c4 = st.columns(2)
            with c3:
                figb = go.Figure()
                if "cws" in d.columns:
                    figb.add_trace(go.Bar(x=x, y=d["cws"], name="CWs", marker_color="#0F766E"))
                if "approved_deals" in d.columns:
                    figb.add_trace(go.Bar(x=x, y=d["approved_deals"], name="Approved", marker_color="#94A3B8"))
                figb.update_layout(title="CWs vs Approved Deals", barmode="group", height=340,
                                   margin=dict(l=10, r=10, t=45, b=10),
                                   legend=dict(orientation="h", y=-0.25), plot_bgcolor="white")
                st.plotly_chart(figb, use_container_width=True)
            with c4:
                st.plotly_chart(line_fig(
                    [("Occupancy", "occupancy", "#2563EB"), ("Live Sold Rate", "live_sold_rate", "#0F766E"),
                     ("Live Sold Rate w/ Approved", "live_sold_rate_approved", "#F59E0B")],
                    "Occupancy vs Live Sold Rates", is_pct=True), use_container_width=True)

    # ---------------- Panel tab ----------------
    with tab_panel:
        months = d["month_label"].tolist()
        row_labels, table_rows = [], []
        for lbl, col, kind in METRICS:
            if col is None:
                row_labels.append("- " + lbl + " -")
                table_rows.append([""] * len(months))
            elif col in d.columns:
                row_labels.append(lbl)
                table_rows.append([fmt(v, kind) for v in d[col].tolist()])
        panel_df = pd.DataFrame(table_rows, index=row_labels, columns=months)
        st.dataframe(panel_df, use_container_width=True,
                     height=min(60 + 35 * len(row_labels), 1250))
        st.caption("Same bridge the Google Sheets panel reads - numbers match the sheet at its last extract pull.")


main()
