"""ME Sales Panel - Streamlit dashboard (BI-infographic style).

Single-canvas dashboard over the BigQuery bridge that also feeds the Google
Sheets panel (css-operations.me_panel_dev_us.me_sales_panel_k_monthly).
Sections: KPI gauges + cards / Revenue / Sales / Mix / Countries (animated map).

Credentials: [gcp_service_account] in .streamlit/secrets.toml, else ADC.
"""
import base64
import math
import os
from decimal import Decimal

import pandas as pd
import streamlit as st

BQ_PROJECT = "css-operations"
BRIDGE_TABLE = "css-operations.me_panel_dev_us.me_sales_panel_k_monthly"
COUNTRIES = ["Middle East", "Saudi Arabia", "UAE", "Kuwait", "Bahrain", "Qatar"]
START_MONTH = "2025-01-31"

# NAMAA brand palette: deep forest green + cream + terracotta (from the brand banner),
# with sage / gold / taupe as supporting series colors. Variable names kept generic so the
# chart code reads unchanged - only the values are branded.
NAVY = "#21362B"          # NAMAA deep green (primary dark)
TEAL = "#5F8575"          # sage green (secondary)
RED = "#B4472E"           # rust - losses/churn
ORANGE = "#D97757"        # terracotta - the brand accent
YELLOW = "#C2A14D"        # sand/gold
SLATE = "#A79E8B"         # taupe
LIGHT = "#EAE7DC"         # warm light (gauge remainder)

SERIES_COLORS = [NAVY, ORANGE, YELLOW, TEAL, RED, SLATE]
COUNTRY_COLORS = {"Saudi Arabia": NAVY, "UAE": ORANGE, "Kuwait": YELLOW, "Bahrain": RED, "Qatar": TEAL}

LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "namaa_logo.jpg")
_page_icon = LOGO_PATH if os.path.exists(LOGO_PATH) else ":bar_chart:"

st.set_page_config(page_title="ME Sales Panel | NAMAA", layout="wide", page_icon=_page_icon,
                   initial_sidebar_state="collapsed")


MOTIF_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "namaa_motif.png")

# ArcGIS Location Platform key for the Esri basemap tiles (same map service family as the
# Talabat site). Override via ARCGIS_API_KEY in secrets; this fallback keeps the map working.
ARCGIS_DEFAULT_KEY = ("AAPTazJyeyXdia4yZ8kifX4yDiw..tmKsfsr3ICm0GmhX-8bLyCDCls6oQi4tGrZizEYySs_"
                      "5IPHbtB5rkpdZc7WBoRiAp9PGgI0sp-WRrnzzuvrzbYqasb1qB_altV_pkh6jbu6YIUEk386"
                      "TZhBDRRN9AQ_nxQfLIE7bVHSdU7gKEABklA-fj-Oc_ktthlJvkHTkYRNwSy9R8Zna-rovVMy"
                      "lRxjlwuqX9AuEWbcA-8sJUlH-G8FandT3O1Dj14qi7_ntgKh5aC_YrK9ebg..AT1_mzOu9Cgs")


@st.cache_data(show_spinner=False)
def _logo_b64() -> str:
    try:
        with open(LOGO_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")
    except Exception:
        return ""


@st.cache_data(show_spinner=False)
def _motif_b64() -> str:
    try:
        with open(MOTIF_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")
    except Exception:
        return ""


def _inject_motif():
    """The terracotta NAMAA line-art, pinned to the top-right corner like the brand banner."""
    _mb = _motif_b64()
    if _mb:
        st.markdown('<img class="nm-motif" src="data:image/png;base64,' + _mb + '"/>',
                    unsafe_allow_html=True)


st.markdown(
    """
    <style>
    .stApp { background: #EEEDE5; }
    #MainMenu, footer { visibility: hidden; }
    .block-container { padding-top: 3.4rem !important; max-width: 100% !important;
                       padding-left: 1.6rem !important; padding-right: 1.6rem !important; }
    header[data-testid="stHeader"] { background: transparent !important; }
    /* NAMAA brand banner */
    .nm-banner { display: flex; align-items: center; gap: 16px; background: #21362B;
                 border-radius: 14px; padding: 10px 18px; margin: 4px 0 12px 0;
                 box-shadow: 0 2px 8px rgba(33, 54, 43, 0.25); }
    .nm-banner img { height: 56px; border-radius: 10px; }
    .nm-name { color: #FFFFFF; font-weight: 800; font-size: 1.1rem; letter-spacing: 0.3em; margin: 0; }
    .nm-sub { color: #C9D5CC; font-size: 0.74rem; font-weight: 700; letter-spacing: 0.14em;
              text-transform: uppercase; margin: 0; }
    .hdr { display: flex; align-items: baseline; gap: 14px; margin-bottom: 4px; }
    .hdr .t { font-size: 1.5rem; font-weight: 800; color: #21362B; letter-spacing: -0.02em; }
    .hdr .badge { background: #E2E6DC; color: #21362B; font-size: 0.75rem; font-weight: 700;
                  padding: 3px 10px; border-radius: 999px; }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: #FFFFFF; border: 1px solid #E0DCCE !important; border-radius: 14px;
        box-shadow: 0 2px 6px rgba(33, 54, 43, 0.08);
    }
    .kpi-l { font-size: 0.72rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
             color: #7C776A; margin: 0; }
    .kpi-v { font-size: 1.5rem; font-weight: 800; color: #21362B; margin: 2px 0 0 0; line-height: 1.1; }
    .kpi-d-up { color: #3F7A52; font-size: 0.78rem; font-weight: 700; }
    .kpi-d-dn { color: #B4472E; font-size: 0.78rem; font-weight: 700; }
    .kpi-d-na { color: #A79E8B; font-size: 0.78rem; font-weight: 600; }
    .g-lbl { text-align: center; font-size: 0.78rem; font-weight: 700; letter-spacing: 0.04em;
             text-transform: uppercase; color: #55604F; margin: -6px 0 0 0; }
    .g-dlt { text-align: center; font-size: 0.74rem; margin: 0; }
    .sec { font-size: 1rem; font-weight: 800; color: #21362B; text-transform: uppercase;
           letter-spacing: 0.06em; margin: 22px 0 4px 0;
           border-left: 5px double #D97757; padding-left: 10px; }
    section[data-testid="stSidebar"], [data-testid="collapsedControl"] { display: none !important; }
    .stDataFrame thead th { background: #F0EEE6 !important; font-weight: 600 !important; }
    /* NAMAA terracotta line-art, top-right corner (brand banner motif) */
    .nm-motif { position: fixed; top: 36px; right: 0; width: 320px; opacity: 0.9;
                z-index: 0; pointer-events: none; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------- data layer
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
                info, scopes=["https://www.googleapis.com/auth/bigquery"]
            )
            job_project = info.get("project_id") or BQ_PROJECT
            return bigquery.Client(project=job_project, credentials=creds)
        except Exception:
            pass
    return bigquery.Client(project=BQ_PROJECT)


@st.cache_data(ttl=900, show_spinner="Loading panel data from BigQuery...")
def load_bridge() -> pd.DataFrame:
    client = _bq_client()
    rows = None
    try:
        query = (
            "SELECT * FROM `" + BRIDGE_TABLE + "` "
            "WHERE month_end >= DATE '" + START_MONTH + "' "
            "AND month_end <= LAST_DAY(CURRENT_DATE(), MONTH) "
            "ORDER BY month_end, country"
        )
        rows = list(client.query(query).result())
    except Exception as query_err:
        try:
            table = client.get_table(BRIDGE_TABLE)
            rows = list(client.list_rows(table))
        except Exception:
            raise query_err
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
        start = pd.Timestamp(START_MONTH)
        end = pd.Timestamp.today().normalize() + pd.offsets.MonthEnd(0)
        df = df[(df["month_end"] >= start) & (df["month_end"] <= end)]
        df = df.sort_values(["month_end", "country"]).reset_index(drop=True)
    return df


def fmt(v, kind):
    try:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return ""
        if kind == "usd":
            return f"${float(v):,.0f}"
        if kind == "usdk":
            x = float(v)
            if abs(x) >= 1_000_000:
                return f"${x / 1_000_000:,.2f}M"
            if abs(x) >= 10_000:
                return f"${x / 1_000:,.0f}k"
            return f"${x:,.0f}"
        if kind == "pct":
            return f"{float(v) * 100:.1f}%"
        if kind == "num1":
            return f"{float(v):,.1f}"
        return f"{float(v):,.0f}"
    except Exception:
        return "" if v is None else str(v)


# Metrics offered in the Countries section (label, column, format kind).
COMPARE_METRICS = [
    ("CWs (kitchens)", "cws", "num"),
    ("Approved Deals", "approved_deals", "num"),
    ("New Occupied Kitchens", "new_occupied_k", "num"),
    ("NRRA $ (net)", "nrra_usd", "usd"),
    ("RRA $ (recognized)", "rra_usd", "usd"),
    ("RRL $ (recognized)", "rrl_usd", "usd"),
    ("RRX $ (accessed)", "xrra_usd", "usd"),
    ("Gross Recurring Revenue $ (EoP)", "gross_rr_usd", "usd"),
    ("RR after MKO/MFO $ (EoP)", "rr_after_mko_mfo_usd", "usd"),
    ("TCV $", "tcv_usd", "usd"),
    ("Approved TCV $", "approved_tcv_usd", "usd"),
    ("Churns (excl. transfers)", "churns_excl_transfers", "num"),
    ("Net Adds", "net_adds", "num"),
    ("Occupancy", "occupancy", "pct"),
    ("Occupied Kitchens", "occupied_kitchens", "num"),
    ("Live - Sold Rate %", "live_sold_rate", "pct"),
    ("Live - Sold Rate w/ Approved %", "live_sold_rate_approved", "pct"),
    ("Sold Rate - All Facilities", "sold_rate_all", "pct"),
]

COUNTRY_ISO = {"Saudi Arabia": "SAU", "UAE": "ARE", "Kuwait": "KWT", "Bahrain": "BHR", "Qatar": "QAT"}


# ---------------------------------------------------------------- access gate
def _allowed_emails() -> set:
    try:
        raw = st.secrets.get("ALLOWED_EMAILS", [])
    except Exception:
        return set()
    if isinstance(raw, str):
        raw = raw.replace(";", ",").split(",")
    return {str(e).strip().lower() for e in raw if str(e).strip()}


def _access_gate():
    allowed = _allowed_emails()
    if not allowed:
        return
    current = (st.session_state.get("me_user_email") or "").strip().lower()
    if current in allowed:
        return
    _b64 = _logo_b64()
    if _b64:
        st.markdown(
            '<div class="nm-banner"><img src="data:image/jpeg;base64,' + _b64 + '"/>'
            '<div><p class="nm-name">NAMAA</p><p class="nm-sub">ME Sales Panel</p></div></div>',
            unsafe_allow_html=True,
        )
    _inject_motif()
    st.write("Enter your work email to open the panel.")
    email = st.text_input("Email", key="me_email_input")
    if st.button("Open", type="primary"):
        if email.strip().lower() in allowed:
            st.session_state["me_user_email"] = email.strip()
            st.rerun()
        else:
            st.error("This email is not on the allowed list. Ask Maysam to add you.")
    st.stop()


# ---------------------------------------------------------------- chart kit
def _go():
    import plotly.graph_objects as go
    return go


def _base_layout(fig, title, height=340):
    fig.update_layout(
        title=dict(text=title, font=dict(size=14, color="#21362B", family="Arial Black, Arial")),
        height=height,
        margin=dict(l=8, r=8, t=44, b=4),
        legend=dict(orientation="h", y=-0.22, font=dict(size=11)),
        plot_bgcolor="white", paper_bgcolor="white",
        hovermode="x unified",
        font=dict(family="Arial", size=11, color="#334155"),
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#E7E4D8", griddash="dot", zerolinecolor="#D9D5C5")
    return fig


def money_axis(fig):
    fig.update_yaxes(tickprefix="$", tickformat="~s")
    return fig


def pct_axis(fig):
    fig.update_yaxes(tickformat=".0%")
    return fig


def add_line(fig, x, y, name, color, closed_idx, width=2.6, msize=8):
    """Dot-marker line (reference style); the stretch after the last closed month is dotted."""
    go = _go()
    solid_end = min(closed_idx, len(x) - 1)
    fig.add_trace(go.Scatter(
        x=x[: solid_end + 1], y=y[: solid_end + 1], mode="lines+markers", name=name,
        line=dict(color=color, width=width),
        marker=dict(size=msize, color="white", line=dict(color=color, width=2.5)),
    ))
    if solid_end < len(x) - 1:
        fig.add_trace(go.Scatter(
            x=x[solid_end:], y=y[solid_end:], mode="lines+markers", name=name,
            line=dict(color=color, width=2, dash="dot"),
            marker=dict(size=msize - 2, color="white", line=dict(color=color, width=2)),
            opacity=0.55, showlegend=False, hoverinfo="skip",
        ))


def add_bar(fig, x, y, name, color, closed_idx):
    go = _go()
    colors = [color if i <= closed_idx else "rgba(148,163,184,0.45)" for i in range(len(x))]
    fig.add_trace(go.Bar(x=x, y=y, name=name, marker_color=colors))


def donut(value, color, delta=None, height=168):
    """KPI ring with the percentage in the center (reference style)."""
    go = _go()
    v = float(value or 0)
    v01 = max(0.0, min(1.0, v))
    fig = go.Figure(go.Pie(values=[v01, 1 - v01], hole=0.74, sort=False, direction="clockwise",
                           marker=dict(colors=[color, LIGHT]), textinfo="none", hoverinfo="skip"))
    fig.add_annotation(text=f"<b>{v * 100:.0f}%</b>", showarrow=False,
                       font=dict(size=22, color="#21362B", family="Arial Black, Arial"))
    fig.update_layout(height=height, margin=dict(l=6, r=6, t=6, b=0),
                      showlegend=False, paper_bgcolor="white")
    return fig


def spark(series, color=TEAL, height=52):
    go = _go()
    fig = go.Figure(go.Scatter(y=list(series), mode="lines",
                               line=dict(color=color, width=2),
                               fill="tozeroy", fillcolor="rgba(33,54,43,0.10)"))
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=2, b=0),
                      plot_bgcolor="white", paper_bgcolor="white", showlegend=False)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def kpi_card(col, label, value_str, delta_val, delta_str, series, up_is_good=True):
    with col:
        with st.container(border=True):
            st.markdown(f'<p class="kpi-l">{label}</p>', unsafe_allow_html=True)
            st.markdown(f'<p class="kpi-v">{value_str}</p>', unsafe_allow_html=True)
            if delta_val is None:
                st.markdown('<span class="kpi-d-na">no prior month</span>', unsafe_allow_html=True)
            else:
                good = (delta_val >= 0) if up_is_good else (delta_val <= 0)
                cls = "kpi-d-up" if good else "kpi-d-dn"
                arrow = "&#9650;" if delta_val >= 0 else "&#9660;"
                st.markdown(f'<span class="{cls}">{arrow} {delta_str} vs prior</span>',
                            unsafe_allow_html=True)
            if series is not None and len(series) > 1:
                st.plotly_chart(spark(series), use_container_width=True,
                                config={"displayModeBar": False, "staticPlot": True})


def stacked_pct(d, x, buckets, title, closed_idx):
    """Colorful 100% stacked bars (reference style). buckets = [(label, col), ...]."""
    go = _go()
    fig = go.Figure()
    for (lbl, cn), color in zip(buckets, SERIES_COLORS):
        if cn in d.columns:
            fig.add_trace(go.Bar(x=x, y=d[cn], name=lbl, marker_color=color))
    fig.update_layout(barmode="stack")
    pct_axis(_base_layout(fig, title))
    return fig


# ---------------------------------------------------------------- All Hands scorecards
# Rows for the two Google Sheet "All Hands" scorecards. Tuples: (label, bridge column, format kind, up_is_good).
# label=None -> spacer row (blank line for visual grouping). up_is_good=True colors positive MoM green.
CK_SCORECARD_METRICS = [
    ("Kitchens sold",     "cws",                          "num",  True),
    ("Approved Deals",    "approved_deals",               "num",  True),
    ("RRA %",             "rra",                          "pct",  True),
    (None, None, None, None),
    ("Kitchens churned",  "churns_excl_transfers",        "num",  False),
    ("RRL %",             "rrl",                          "pct",  False),
    (None, None, None, None),
    ("Net Adds",          "net_adds",                     "num",  True),
    ("NRRA %",            "nrra",                         "pct",  True),
    (None, None, None, None),
    ("All AE Prod.",      "sales_team_cw_productivity",   "num1", True),
    (None, None, None, None),
    ("Live kitchens",     "total_kitchens",               "num",  True),
    (None, None, None, None),
    ("Live Sold",         "live_sold_rate",               "pct",  True),
    ("Occupancy",         "occupancy",                    "pct",  True),
    (None, None, None, None),
    ("Occupied Kx",       "occupied_kitchens",            "num",  True),
]

CR_SCORECARD_METRICS = [
    ("Cloud Retail CWs",       "cr_cws",       "num", True),
    ("CR RRA $",               "cr_rra_usd",   "usd", True),
    (None, None, None, None),
    ("Cloud Retail Churns",    "cr_churns",    "num", False),
    ("CR RRL $",               "cr_rrl_usd",   "usd", False),
    (None, None, None, None),
    ("Cloud Retail Net Adds",  "cr_net_adds",  "num", True),  # calculated: cr_cws - cr_churns
    ("CR NRRA $",              "cr_nrra_usd",  "usd", True),
]

SCORECARD_REGIONS = ["Middle East", "UAE", "Saudi Arabia", "Kuwait"]
SCORECARD_REGION_DISPLAY = {"Saudi Arabia": "KSA"}


def _render_all_hands_scorecard(df, all_months, metrics_spec, key_prefix):
    """Reproduce the Google Sheet All Hands scorecard layout: 4 region blocks side-by-side,
    each with the last 3 months (as-of picker) + a MoM Δ column, one row per metric.
    Negative MoM in red / positive in green (unless up_is_good=False, then flipped)."""
    if df is None or df.empty or not all_months:
        st.info("No panel data available.")
        return

    # Add calculated cr_net_adds if the two ingredients are there.
    if any(m[1] == "cr_net_adds" for m in metrics_spec if m[1]) \
            and "cr_net_adds" not in df.columns \
            and {"cr_cws", "cr_churns"} <= set(df.columns):
        df = df.copy()
        df["cr_net_adds"] = df["cr_cws"] - df["cr_churns"]

    # As-of month picker (newest first).
    month_labels = [pd.Timestamp(m).strftime("%b %Y") for m in all_months]
    labels_desc = list(reversed(month_labels))
    sel_label = st.selectbox(
        "As-of month",
        options=labels_desc,
        index=0,
        key=f"{key_prefix}_scorecard_asof",
    )
    sel_idx = month_labels.index(sel_label)
    if sel_idx < 2:
        st.warning("Need at least 3 months of history to build the scorecard. "
                   "Pick a more recent as-of month or wait for more data.")
        return
    win = all_months[sel_idx - 2: sel_idx + 1]  # oldest, mid, newest (as-of)
    win_hdrs = [pd.Timestamp(m).strftime("%b %y") for m in win]

    # Build one HTML table so we can lay out 4 region blocks side-by-side.
    n_regions = len(SCORECARD_REGIONS)
    total_cols = 1 + n_regions * 4  # metric label + (3 months + MoM) per region
    html = [
        "<div class='scorecard-wrap'>",
        f"<div class='scorecard-title'>{sel_label}</div>",
        "<table class='scorecard'>",
        "<colgroup>",
        "<col class='c-label'/>",
    ]
    for _ in SCORECARD_REGIONS:
        html += ["<col/>", "<col/>", "<col/>", "<col class='c-delta'/>"]
    html.append("</colgroup>")

    # Region banner row.
    html.append("<thead>")
    html.append("<tr>")
    html.append("<th class='sc-empty'></th>")
    for r in SCORECARD_REGIONS:
        html.append(f"<th class='sc-region' colspan='4'>{SCORECARD_REGION_DISPLAY.get(r, r)}</th>")
    html.append("</tr>")
    # Month subheader.
    html.append("<tr>")
    html.append("<th class='sc-empty'></th>")
    for _ in SCORECARD_REGIONS:
        for h in win_hdrs:
            html.append(f"<th class='sc-month'>{h}</th>")
        html.append("<th class='sc-month'>MoM Δ</th>")
    html.append("</tr>")
    html.append("</thead><tbody>")

    for label, col, kind, up_good in metrics_spec:
        if label is None:
            html.append(f"<tr class='sc-spacer'><td colspan='{total_cols}'>&nbsp;</td></tr>")
            continue
        html.append("<tr>")
        html.append(f"<td class='sc-metric'>{label}</td>")
        for region in SCORECARD_REGIONS:
            row = df[(df["country"] == region) & (df["month_end"].isin(win))]
            vals = []
            for m in win:
                r = row[row["month_end"] == m]
                v = r[col].iloc[0] if (col in row.columns and not r.empty) else None
                try:
                    v = None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)
                except Exception:
                    v = None
                vals.append(v)
            for v in vals:
                html.append(f"<td class='sc-val'>{fmt(v, kind) if v is not None else '—'}</td>")
            mom = (vals[-1] - vals[-2]) if (vals[-1] is not None and vals[-2] is not None) else None
            if mom is None:
                mom_cls = "sc-delta-na"
                mom_txt = "—"
            else:
                if abs(mom) < 1e-12:
                    mom_cls, mom_txt = "sc-delta-flat", fmt(mom, kind)
                else:
                    good = (mom > 0) if up_good else (mom < 0)
                    mom_cls = "sc-delta-up" if good else "sc-delta-dn"
                    mom_txt = fmt(mom, kind)
            html.append(f"<td class='sc-delta {mom_cls}'>{mom_txt}</td>")
        html.append("</tr>")

    html.append("</tbody></table></div>")

    st.markdown(
        """
        <style>
        .scorecard-wrap { overflow-x: auto; padding: 6px 0 18px 0; }
        .scorecard-title { font-size: 1.1rem; font-weight: 800; color: #1F3B57; margin: 6px 0 10px 2px; }
        table.scorecard { border-collapse: separate; border-spacing: 0; width: 100%;
                          font-family: Arial, sans-serif; font-size: 0.85rem; background: #F5F1E7; }
        table.scorecard th, table.scorecard td { padding: 6px 10px; text-align: right; white-space: nowrap; }
        table.scorecard col.c-label { width: 190px; }
        table.scorecard col.c-delta { width: 82px; }
        table.scorecard th.sc-empty { background: transparent; }
        table.scorecard th.sc-region { background: transparent; color: #1F3B57; font-weight: 800;
                                       text-align: center; font-size: 1rem; padding-bottom: 4px; }
        table.scorecard th.sc-month { background: #21362B; color: #FFFFFF; font-weight: 700;
                                      text-align: center; font-size: 0.78rem; letter-spacing: 0.02em; }
        table.scorecard td.sc-metric { text-align: left; font-weight: 700; color: #21362B; }
        table.scorecard td.sc-val { color: #21362B; font-weight: 600; }
        table.scorecard td.sc-delta { font-weight: 800; }
        table.scorecard .sc-delta-up { color: #16A34A; }
        table.scorecard .sc-delta-dn { color: #E74C3C; }
        table.scorecard .sc-delta-flat { color: #64748B; }
        table.scorecard .sc-delta-na { color: #94A3B8; }
        table.scorecard tr.sc-spacer td { padding: 4px 0; background: transparent; }
        </style>
        """ + "".join(html),
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------- Panel Overview (existing dashboard)
def _render_panel_overview(df, all_months, all_labels, cur_month_start):
    """Existing 'Panel Overview' - filter bar, KPI gauges, KPI cards, Revenue,
    Sales & Churn, Mix, Countries map + comparison, footer. Rendered inside the
    'Panel Overview' tab. Banner and BQ load happen once in main() and are shared
    across tabs, so both are stripped from here."""
    # ---- top filter bar (pills + period presets); no page title - the browser tab carries the name ----
    FLAG = {"Middle East": "\U0001F30D", "Saudi Arabia": "\U0001F1F8\U0001F1E6",
            "UAE": "\U0001F1E6\U0001F1EA", "Kuwait": "\U0001F1F0\U0001F1FC",
            "Bahrain": "\U0001F1E7\U0001F1ED", "Qatar": "\U0001F1F6\U0001F1E6"}
    countries = [c for c in COUNTRIES if c in set(df["country"])]
    disp = {c: (FLAG.get(c, "") + " " + c).strip() for c in countries}
    rev = {v: k for k, v in disp.items()}

    def _picker(label, options, default, key):
        """Segmented pills with graceful fallback for older Streamlit versions."""
        try:
            v = st.segmented_control(label, options, default=default, key=key)
        except Exception:
            try:
                v = st.pills(label, options, default=default, key=key)
            except Exception:
                v = st.selectbox(label, options, index=options.index(default), key=key)
        return v or default

    with st.container(border=True):
        r1a, r1b = st.columns([5.2, 0.8], vertical_alignment="bottom")
        with r1a:
            sel_disp = _picker("Market", list(disp.values()), disp[countries[0]], "flt_cty")
            sel_country = rev.get(sel_disp, countries[0])
        with r1b:
            try:
                _refresh = st.button("Refresh", icon=":material/refresh:", use_container_width=True)
            except TypeError:
                _refresh = st.button("Refresh", use_container_width=True)
            if _refresh:
                load_bridge.clear()
                st.rerun()
        r2a, r2b = st.columns([4, 2], vertical_alignment="center")
        with r2a:
            period = _picker("Period", ["3M", "6M", "12M", "YTD", "All", "Custom"], "All", "flt_period")
        with r2b:
            st.caption("Bridge through **" + all_labels[-1] + "** - refreshed every 12h, "
                       "same source as the Sheets panel")
        custom_rng = None
        if period == "Custom":
            try:
                _pop = st.popover("Pick a custom month range")
            except Exception:
                _pop = st.container()
            with _pop:
                if len(all_labels) > 1:
                    custom_rng = st.select_slider("Months", options=all_labels,
                                                  value=(all_labels[0], all_labels[-1]))

    # Resolve the month window from the preset.
    if period == "Custom" and custom_rng:
        i0, i1 = all_labels.index(custom_rng[0]), all_labels.index(custom_rng[1])
        if i0 > i1:
            i0, i1 = i1, i0
        keep = all_months[i0:i1 + 1]
    elif period in ("3M", "6M", "12M"):
        n = int(period[:-1])
        keep = all_months[-(n + 1):]  # last N closed months + the current partial one
    elif period == "YTD":
        _yr = pd.Timestamp.today().year
        keep = [m for m in all_months if pd.Timestamp(m).year == _yr] or all_months
    else:
        keep = all_months
    keep_months = set(keep)

    d = df[(df["country"] == sel_country) & (df["month_end"].isin(keep_months))]
    d = d.sort_values("month_end").reset_index(drop=True)
    if d.empty:
        st.info("No rows for this selection.")
        st.stop()
    x = d["month_label"].tolist()

    closed_mask = d["month_end"] < cur_month_start
    closed_idx = int(closed_mask[closed_mask].index.max()) if closed_mask.any() else len(d) - 1
    kpi_row = d.iloc[closed_idx]
    kpi_prev = d.iloc[closed_idx - 1] if closed_idx > 0 else None

    st.markdown(
        '<div class="hdr">'
        f'<span class="badge">{sel_country}</span>'
        f'<span class="badge">KPIs as of {kpi_row["month_label"]} (last closed month)</span></div>',
        unsafe_allow_html=True,
    )

    def kd(col_name):
        try:
            if kpi_prev is None or col_name not in d.columns:
                return None
            return float(kpi_row[col_name]) - float(kpi_prev[col_name])
        except Exception:
            return None

    def kseries(col_name):
        if col_name not in d.columns:
            return None
        return d[col_name].iloc[: closed_idx + 1].fillna(0).tolist()

    # ---- KPI ring gauges (percent metrics) ----
    conc_now = None
    conc_prev = None
    if {"gross_rr_usd", "rr_after_mko_mfo_usd"} <= set(d.columns):
        try:
            g, n = float(kpi_row["gross_rr_usd"]), float(kpi_row["rr_after_mko_mfo_usd"])
            conc_now = (g - n) / g if g else None
            if kpi_prev is not None:
                gp, np_ = float(kpi_prev["gross_rr_usd"]), float(kpi_prev["rr_after_mko_mfo_usd"])
                conc_prev = (gp - np_) / gp if gp else None
        except Exception:
            pass

    GAUGES = [
        ("Occupancy", kpi_row.get("occupancy"), kd("occupancy"), NAVY, True),
        ("Live Sold Rate", kpi_row.get("live_sold_rate"), kd("live_sold_rate"), TEAL, True),
        ("Live Sold Rate w/ Approved", kpi_row.get("live_sold_rate_approved"),
         kd("live_sold_rate_approved"), ORANGE, True),
        ("Concession Load", conc_now,
         (conc_now - conc_prev) if (conc_now is not None and conc_prev is not None) else None,
         RED, False),
    ]
    gcols = st.columns(4)
    for (lbl, val, dv, color, up_good), gcol in zip(GAUGES, gcols):
        with gcol:
            with st.container(border=True):
                st.plotly_chart(donut(val, color), use_container_width=True,
                                config={"displayModeBar": False, "staticPlot": True})
                st.markdown(f'<p class="g-lbl">{lbl}</p>', unsafe_allow_html=True)
                if dv is None:
                    st.markdown('<p class="g-dlt kpi-d-na">-</p>', unsafe_allow_html=True)
                else:
                    good = (dv >= 0) if up_good else (dv <= 0)
                    cls = "kpi-d-up" if good else "kpi-d-dn"
                    arrow = "&#9650;" if dv >= 0 else "&#9660;"
                    st.markdown(f'<p class="g-dlt"><span class="{cls}">{arrow} {dv * 100:+.1f} pp</span></p>',
                                unsafe_allow_html=True)

    # ---- KPI number cards ----
    KPIS = [
        ("CWs", "cws", "num", True),
        ("Approved Deals", "approved_deals", "num", True),
        ("New Occupied Kitchens", "new_occupied_k", "num", True),
        ("NRRA $", "nrra_usd", "usdk", True),
        ("Gross RR $ (EoP)", "gross_rr_usd", "usdk", True),
    ]
    slots = st.columns(len(KPIS))
    for (label, col_name, kind, up_good), slot in zip(KPIS, slots):
        if col_name not in d.columns:
            continue
        dv = kd(col_name)
        dstr = fmt(abs(dv) if dv is not None else None, kind)
        kpi_card(slot, label, fmt(kpi_row.get(col_name), kind), dv, dstr, kseries(col_name), up_good)

    go = _go()

    # ---- Revenue ----
    st.markdown('<p class="sec">Revenue</p>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        fig = go.Figure()
        for lbl, cn, color in [("RRA $", "rra_usd", TEAL), ("RRL $", "rrl_usd", RED),
                               ("NRRA $", "nrra_usd", NAVY)]:
            if cn in d.columns:
                add_line(fig, x, d[cn].tolist(), lbl, color, closed_idx)
        money_axis(_base_layout(fig, "Recurring Revenue - added / lost / net"))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    with c2:
        fig = go.Figure()
        for lbl, cn, color in [("Gross RR $", "gross_rr_usd", NAVY),
                               ("RR after MKO/MFO $", "rr_after_mko_mfo_usd", ORANGE)]:
            if cn in d.columns:
                add_line(fig, x, d[cn].tolist(), lbl, color, closed_idx)
        money_axis(_base_layout(fig, "Occupied-kitchen revenue at EoP (gap = concessions)"))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ---- Sales & Churn ----
    st.markdown('<p class="sec">Sales &amp; Churn</p>', unsafe_allow_html=True)
    c3, c4 = st.columns(2)
    with c3:
        fig = go.Figure()
        if "cws" in d.columns:
            add_bar(fig, x, d["cws"].tolist(), "CWs", TEAL, closed_idx)
        if "approved_deals" in d.columns:
            add_bar(fig, x, d["approved_deals"].tolist(), "Approved", NAVY, closed_idx)
        if "churns_excl_transfers" in d.columns:
            add_bar(fig, x, d["churns_excl_transfers"].tolist(), "Churns", RED, closed_idx)
        _base_layout(fig, "CWs vs Approved vs Churns")
        fig.update_layout(barmode="group")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    with c4:
        fig = go.Figure()
        if "tcv_usd" in d.columns:
            add_line(fig, x, d["tcv_usd"].tolist(), "TCV $", NAVY, closed_idx)
        if "approved_tcv_usd" in d.columns:
            add_line(fig, x, d["approved_tcv_usd"].tolist(), "Approved TCV $", ORANGE, closed_idx)
        money_axis(_base_layout(fig, "TCV vs Approved TCV"))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ---- Mix (stacked distributions) ----
    st.markdown('<p class="sec">Mix</p>', unsafe_allow_html=True)
    c5, c6 = st.columns(2)
    with c5:
        st.plotly_chart(stacked_pct(
            d, x,
            [("Start-ups", "rr_pct_startups"), ("Independents", "rr_pct_independents"),
             ("Growth", "rr_pct_growth"), ("Enterprise", "rr_pct_enterprise")],
            "Recurring Revenue by account type", closed_idx),
            use_container_width=True, config={"displayModeBar": False})
    with c6:
        st.plotly_chart(stacked_pct(
            d, x,
            [("<= 6m", "cw_term_lte_6m"), ("7-12m", "cw_term_7_12m"),
             ("13-18m", "cw_term_13_18m"), ("19-24m", "cw_term_19_24m"),
             ("25-36m", "cw_term_25_36m"), ("> 36m", "cw_term_gt_36m")],
            "CW term mix", closed_idx),
            use_container_width=True, config={"displayModeBar": False})

    # ---- Countries (map + comparison) ----
    st.markdown('<p class="sec">Countries</p>', unsafe_allow_html=True)
    labels = [l for (l, c, k) in COMPARE_METRICS if c in df.columns]
    default_lbl = "NRRA $ (net)" if "NRRA $ (net)" in labels else labels[0]
    sel_label = st.selectbox("Metric", labels, index=labels.index(default_lbl))
    sel_col, sel_kind = next((c, k) for (l, c, k) in COMPARE_METRICS if l == sel_label)

    dc = df[(df["month_end"].isin(keep_months)) & (df["country"] != "Middle East")].copy()
    dme = df[(df["month_end"].isin(keep_months)) & (df["country"] == "Middle East")].sort_values("month_end")

    m1, m2 = st.columns([3, 2])
    with m1:
        # Real Esri basemap (ArcGIS tiles - same map service the Talabat site uses), with a
        # month slider. Static per month: sturdier than plotly's frame animation on tile maps.
        try:
            _win_labels = [pd.Timestamp(m).strftime("%b %Y") for m in sorted(keep_months)]
            if len(_win_labels) > 1:
                _map_month = st.select_slider("Map month", options=_win_labels,
                                              value=(kpi_row["month_label"]
                                                     if kpi_row["month_label"] in _win_labels
                                                     else _win_labels[-1]),
                                              key="map_month")
            else:
                _map_month = _win_labels[0]
            snapm = dc[dc["month_label"] == _map_month].dropna(subset=[sel_col]).copy()
            if snapm.empty:
                st.info("No data for this month.")
            else:
                go = _go()
                cts = snapm["country"].tolist()
                vals = snapm[sel_col].astype(float).tolist()
                _vmax = max(abs(v) for v in vals) or 1.0
                sizes = [16 + 30 * (abs(v) / _vmax) for v in vals]
                mk = dict(size=sizes, color=[COUNTRY_COLORS.get(c, SLATE) for c in cts],
                          opacity=0.88)
                texts = [f"<b>{c}</b><br>{fmt(v, sel_kind)}" for c, v in zip(cts, vals)]
                lats = [COUNTRY_CENTROID[c][0] for c in cts]
                lons = [COUNTRY_CENTROID[c][1] for c in cts]
                try:
                    _token = str(st.secrets.get("ARCGIS_API_KEY", "")).strip()
                except Exception:
                    _token = ""
                _token = _token or ARCGIS_DEFAULT_KEY
                tile_url = ("https://static-map-tiles-api.arcgis.com/arcgis/rest/services/"
                            "static-basemap-tiles-service/v1/arcgis/navigation/static/tile/"
                            "{z}/{y}/{x}?token=" + _token)
                map_cfg = dict(style="white-bg", center=dict(lat=26.0, lon=49.6), zoom=4.3,
                               layers=[dict(below="traces", sourcetype="raster",
                                            source=[tile_url])])
                try:
                    fig = go.Figure(go.Scattermap(
                        lat=lats, lon=lons, mode="markers+text", marker=mk, text=texts,
                        textposition="top center", textfont=dict(size=12, color="#21362B"),
                        hoverinfo="text"))
                    fig.update_layout(map=map_cfg)
                except (AttributeError, ValueError):
                    fig = go.Figure(go.Scattermapbox(
                        lat=lats, lon=lons, mode="markers+text", marker=mk, text=texts,
                        textposition="top center", textfont=dict(size=12, color="#21362B"),
                        hoverinfo="text"))
                    fig.update_layout(mapbox=map_cfg)
                fig.update_layout(
                    title=dict(text=f"{sel_label} - {_map_month}",
                               font=dict(size=14, color="#21362B", family="Arial Black, Arial")),
                    height=470, margin=dict(l=4, r=4, t=44, b=4), paper_bgcolor="white",
                    showlegend=False)
                fig.add_annotation(text="Powered by Esri", x=1, y=0, xref="paper", yref="paper",
                                   showarrow=False, xanchor="right", yanchor="bottom",
                                   font=dict(size=9, color="#7C776A"))
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        except Exception as _map_err:
            st.info("Map unavailable: " + str(_map_err)[:160])
    with m2:
        snap = dc[dc["month_end"] == kpi_row["month_end"]].dropna(subset=[sel_col]).sort_values(sel_col)
        fig = go.Figure(go.Bar(
            x=snap[sel_col], y=snap["country"], orientation="h",
            marker_color=[COUNTRY_COLORS.get(c, SLATE) for c in snap["country"]],
            text=[fmt(v, sel_kind) for v in snap[sel_col]], textposition="outside",
        ))
        _base_layout(fig, f"{sel_label} - {kpi_row['month_label']}", height=470)
        fig.update_xaxes(showticklabels=False)
        fig.update_layout(margin=dict(l=8, r=70, t=44, b=4))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    t1, t2 = st.columns(2)
    with t1:
        fig = go.Figure()
        for cty in [c for c in COUNTRIES if c != "Middle East"]:
            dd = dc[dc["country"] == cty].sort_values("month_end")
            if not dd.empty and sel_col in dd.columns:
                fig.add_trace(go.Scatter(
                    x=dd["month_label"], y=dd[sel_col], mode="lines+markers", name=cty,
                    line=dict(color=COUNTRY_COLORS.get(cty, SLATE), width=2.2),
                    marker=dict(size=6, color="white",
                                line=dict(color=COUNTRY_COLORS.get(cty, SLATE), width=2)),
                ))
        _base_layout(fig, f"{sel_label} - trend by country", height=380)
        if sel_kind == "usd":
            money_axis(fig)
        elif sel_kind == "pct":
            pct_axis(fig)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    with t2:
        # Country share of ME, stacked by month (last 6 closed months) - only for additive metrics.
        if sel_kind != "pct":
            closed = dc[dc["month_end"] < cur_month_start].sort_values("month_end")
            last_m = sorted(closed["month_end"].unique())[-6:]
            fig = go.Figure()
            for cty in [c for c in COUNTRIES if c != "Middle East"]:
                dd = closed[(closed["country"] == cty) & (closed["month_end"].isin(last_m))]
                dd = dd.sort_values("month_end")
                if not dd.empty and sel_col in dd.columns:
                    fig.add_trace(go.Bar(
                        y=[pd.Timestamp(m).strftime("%b %Y") for m in dd["month_end"]],
                        x=dd[sel_col], name=cty, orientation="h",
                        marker_color=COUNTRY_COLORS.get(cty, SLATE),
                    ))
            fig.update_layout(barmode="stack")
            _base_layout(fig, f"{sel_label} - country mix, last 6 closed months", height=380)
            if sel_kind == "usd":
                fig.update_xaxes(tickprefix="$", tickformat="~s")
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.caption("Country-mix stack is shown for additive metrics (counts and $), not rates.")

    # ---- branded footer ----
    fcol1, fcol2 = st.columns([0.25, 9.75], vertical_alignment="center")
    with fcol1:
        if os.path.exists(LOGO_PATH):
            st.image(LOGO_PATH, width=36)
    with fcol2:
        st.caption("**NAMAA - ME RevOps** | Source: `" + BRIDGE_TABLE + "` - same bridge the "
                   "Google Sheets panel reads; rebuilt every 12h. Current partial month is "
                   "dotted/grey and excluded from KPIs.")


# ---------------------------------------------------------------- main
def main():
    """Access gate + load BQ bridge once, then dispatch to three tabs:
    Panel Overview (existing dashboard) / ME All Hands Slides (Cloud Kitchens
    scorecard) / CR ME All Hands Slides (Cloud Retail scorecard)."""
    _access_gate()

    try:
        df = load_bridge()
    except Exception as e:
        st.error("Could not load the bridge from BigQuery. Check credentials.\n\nDetails: " + str(e))
        st.stop()
    if df.empty:
        st.warning("The bridge returned no rows.")
        st.stop()

    df["month_label"] = df["month_end"].dt.strftime("%b %Y")
    all_months = sorted(df["month_end"].unique())
    all_labels = [pd.Timestamp(m).strftime("%b %Y") for m in all_months]
    cur_month_start = pd.Timestamp.today().normalize().replace(day=1)

    # Banner persists across all tabs.
    _b64 = _logo_b64()
    if _b64:
        st.markdown(
            '<div class="nm-banner"><img src="data:image/jpeg;base64,' + _b64 + '"/>'
            '<div><p class="nm-name">NAMAA</p><p class="nm-sub">ME Sales Panel</p></div></div>',
            unsafe_allow_html=True,
        )
    _inject_motif()

    tab_overview, tab_ck, tab_cr = st.tabs([
        "Panel Overview",
        "ME All Hands Slides",
        "CR ME All Hands Slides",
    ])
    with tab_overview:
        _render_panel_overview(df, all_months, all_labels, cur_month_start)
    with tab_ck:
        _render_all_hands_scorecard(df, all_months, CK_SCORECARD_METRICS, "ck")
    with tab_cr:
        _render_all_hands_scorecard(df, all_months, CR_SCORECARD_METRICS, "cr")


main()
