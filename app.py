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
    /* Auto-insight line under section headers */
    .nm-insight { background: #FBFAF3; border-left: 3px solid #D97757; border-radius: 8px;
                  padding: 7px 12px; margin: 2px 0 10px 0; color: #4A5548;
                  font-size: 0.84rem; }
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
COUNTRY_CENTROID = {  # (lat, lon) for the map bubbles; Bahrain nudged off Qatar
    "Saudi Arabia": (24.0, 44.5), "UAE": (23.6, 54.2), "Kuwait": (29.6, 47.6),
    "Bahrain": (26.9, 50.4), "Qatar": (24.9, 51.2),
}


# ---------------------------------------------------------------- access gate
def _allowed_emails() -> set:
    try:
        raw = st.secrets.get("ALLOWED_EMAILS", [])
    except Exception:
        return set()
    if isinstance(raw, str):
        raw = raw.replace(";", ",").split(",")
    return {str(e).strip().lower() for e in raw if str(e).strip()}


DEV_EMAILS_DEFAULT = {"maysam.abukashabeh@namaame.com"}


def _is_developer() -> bool:
    """Developer-only controls (e.g. the Refresh button). Override list via
    DEVELOPER_EMAILS in secrets. With no allowlist configured (local run) everyone
    on the machine is the developer."""
    try:
        raw = st.secrets.get("DEVELOPER_EMAILS", [])
    except Exception:
        raw = []
    if isinstance(raw, str):
        raw = raw.replace(";", ",").split(",")
    devs = {str(e).strip().lower() for e in raw if str(e).strip()} or DEV_EMAILS_DEFAULT
    if not _allowed_emails():
        return True
    return (st.session_state.get("me_user_email") or "").strip().lower() in devs


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


def add_line(fig, x, y, name, color, closed_idx, width=2.6, msize=8, fmt_kind=None):
    """Dot-marker line (reference style); the stretch after the last closed month is dotted.
    fmt_kind formats the hover value ($ / % / count) instead of raw floats."""
    go = _go()
    solid_end = min(closed_idx, len(x) - 1)
    cd = [fmt(v, fmt_kind) for v in y] if fmt_kind else None
    ht = "<b>%{fullData.name}</b>: %{customdata}<extra></extra>" if fmt_kind else None
    fig.add_trace(go.Scatter(
        x=x[: solid_end + 1], y=y[: solid_end + 1], mode="lines+markers", name=name,
        line=dict(color=color, width=width),
        marker=dict(size=msize, color="white", line=dict(color=color, width=2.5)),
        customdata=(cd[: solid_end + 1] if cd else None), hovertemplate=ht,
    ))
    if solid_end < len(x) - 1:
        fig.add_trace(go.Scatter(
            x=x[solid_end:], y=y[solid_end:], mode="lines+markers", name=name,
            line=dict(color=color, width=2, dash="dot"),
            marker=dict(size=msize - 2, color="white", line=dict(color=color, width=2)),
            opacity=0.55, showlegend=False, hoverinfo="skip",
        ))


def add_bar(fig, x, y, name, color, closed_idx, fmt_kind=None):
    go = _go()
    colors = [color if i <= closed_idx else "rgba(148,163,184,0.45)" for i in range(len(x))]
    cd = [fmt(v, fmt_kind) for v in y] if fmt_kind else None
    ht = "<b>%{fullData.name}</b>: %{customdata}<extra></extra>" if fmt_kind else None
    fig.add_trace(go.Bar(x=x, y=y, name=name, marker_color=colors,
                         customdata=cd, hovertemplate=ht))


def sec(title, subtitle=None):
    """Section header with an optional inline explainer."""
    sub = ('<span style="font-weight:600; font-size:0.78rem; color:#7C776A; '
           'text-transform:none; letter-spacing:0; margin-left:10px;">' + subtitle + "</span>"
           ) if subtitle else ""
    st.markdown(f'<p class="sec">{title}{sub}</p>', unsafe_allow_html=True)


def insight(text_html):
    """Auto-computed takeaway line under a section header."""
    st.markdown(f'<div class="nm-insight">{text_html}</div>', unsafe_allow_html=True)


def _chart_with_select(fig, key, config):
    """plotly_chart with click-selection when the Streamlit version supports it."""
    try:
        return st.plotly_chart(fig, use_container_width=True, key=key,
                               on_select="rerun", config=config)
    except TypeError:
        st.plotly_chart(fig, use_container_width=True, config=config)
        return None


def _clicked_country(ev):
    """Extract the clicked country from a plotly selection event (customdata carries it)."""
    try:
        pts = ev.selection.points
    except Exception:
        try:
            pts = ev["selection"]["points"]
        except Exception:
            return None
    if not pts:
        return None
    cd = pts[0].get("customdata")
    if isinstance(cd, (list, tuple)):
        cd = cd[0] if cd else None
    return str(cd) if cd else None


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


def kpi_card(col, label, value_str, delta_val, delta_str, series, up_is_good=True,
             delta_label="vs prior"):
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
                st.markdown(f'<span class="{cls}">{arrow} {delta_str} {delta_label}</span>',
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
    ("Owned sites",       "all_facilities",               "num",  True),
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


def _scorecard_cell_values(df, metrics_spec, win):
    """Prep the (values, mom, state) grid used by both the HTML render and the PPTX export.
    Returns (grid, df_maybe_augmented) where grid is a list of {label, kind, regions=[...]}
    or {spacer: True} entries."""
    if any(m[1] == "cr_net_adds" for m in metrics_spec if m[1]) \
            and "cr_net_adds" not in df.columns \
            and {"cr_cws", "cr_churns"} <= set(df.columns):
        df = df.copy()
        df["cr_net_adds"] = df["cr_cws"] - df["cr_churns"]
    grid = []
    for i, (label, col, kind, up_good) in enumerate(metrics_spec):
        if label is None:
            grid.append({"spacer": True})
            continue
        # A row "closes a group" when the very next entry is a spacer OR it is the last row.
        # Used to draw the horizontal underline between metric groups, matching the sheet.
        next_i = i + 1
        is_group_end = (
            next_i >= len(metrics_spec)
            or metrics_spec[next_i][0] is None
        )
        row = {"label": label, "kind": kind, "regions": [], "group_end": is_group_end}
        for region in SCORECARD_REGIONS:
            r = df[(df["country"] == region) & (df["month_end"].isin(win))]
            vals = []
            for m in win:
                rr = r[r["month_end"] == m]
                v = rr[col].iloc[0] if (col in r.columns and not rr.empty) else None
                try:
                    v = None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)
                except Exception:
                    v = None
                vals.append(v)
            mom = (vals[-1] - vals[-2]) if (vals[-1] is not None and vals[-2] is not None) else None
            if mom is None:
                state = "na"
            elif abs(mom) < 1e-12:
                state = "flat"
            else:
                good = (mom > 0) if up_good else (mom < 0)
                state = "up" if good else "dn"
            row["regions"].append({"vals": vals, "mom": mom, "state": state})
        grid.append(row)
    return grid, df


def _pptx_style_cell(cell, *, bold=False, size=10, align="left", color=(0x21, 0x36, 0x2B), fill=None):
    """Apply font + alignment + fill to a python-pptx table cell. All three color styles
    (bold, size, color, alignment) must be applied AFTER the cell.text assignment because
    setting .text discards any previous run styling."""
    from pptx.util import Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    tf = cell.text_frame
    tf.margin_left = tf.margin_right = 0
    tf.margin_top = tf.margin_bottom = 0
    align_map = {"left": PP_ALIGN.LEFT, "right": PP_ALIGN.RIGHT, "center": PP_ALIGN.CENTER}
    for p in tf.paragraphs:
        p.alignment = align_map.get(align, PP_ALIGN.LEFT)
        for r in p.runs:
            r.font.bold = bool(bold)
            r.font.size = Pt(size)
            r.font.color.rgb = RGBColor(*color)
    if fill is not None:
        cell.fill.solid()
        cell.fill.fore_color.rgb = RGBColor(*fill)


def _pptx_cell_bottom_border(cell, *, color_hex="B7B0A0", width_emu=6350):
    """Add a bottom border to a python-pptx table cell. python-pptx has no first-class
    cell-border API, so we build the OOXML fragment (a:lnB) directly on the cell's tcPr."""
    from lxml import etree
    ns_a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    tc = cell._tc
    tcPr = tc.find(f"{{{ns_a}}}tcPr")
    if tcPr is None:
        tcPr = etree.SubElement(tc, f"{{{ns_a}}}tcPr")
    # Remove any prior bottom border so we do not stack styles.
    for old in tcPr.findall(f"{{{ns_a}}}lnB"):
        tcPr.remove(old)
    lnB = etree.SubElement(tcPr, f"{{{ns_a}}}lnB")
    lnB.set("w", str(width_emu))
    lnB.set("cap", "flat")
    lnB.set("cmpd", "sng")
    lnB.set("algn", "ctr")
    solid = etree.SubElement(lnB, f"{{{ns_a}}}solidFill")
    srgb = etree.SubElement(solid, f"{{{ns_a}}}srgbClr")
    srgb.set("val", color_hex)


def _brand_slide(slide, prs, *, slide_number=None):
    """Paint the NAMAA deck chrome on a blank slide: cream background, NAMAA logo
    top-left, terracotta motif bottom-right, confidential footer bottom-left,
    slide number bottom-right. Matches the reference deck template."""
    from pptx.util import Inches, Pt, Emu
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE

    slide_w = prs.slide_width
    slide_h = prs.slide_height

    # Background: NAMAA cream. python-pptx exposes slide.background.fill,
    # so no XML mangling is needed for this.
    try:
        bg = slide.background
        bg.fill.solid()
        bg.fill.fore_color.rgb = RGBColor(0xEE, 0xED, 0xE5)
    except Exception:
        # Some template variants block programmatic background changes; fall back to
        # a full-slide cream rectangle behind everything else.
        rect = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, slide_w, slide_h)
        rect.fill.solid()
        rect.fill.fore_color.rgb = RGBColor(0xEE, 0xED, 0xE5)
        rect.line.fill.background()
        # Send behind everything else (best-effort).
        try:
            spTree = rect._element.getparent()
            spTree.remove(rect._element)
            spTree.insert(2, rect._element)
        except Exception:
            pass

    # NAMAA logo top-left. Height is roughly the header band; width auto-scales.
    if os.path.exists(LOGO_PATH):
        try:
            slide.shapes.add_picture(
                LOGO_PATH,
                left=Inches(0.45),
                top=Inches(0.35),
                height=Inches(0.55),
            )
        except Exception:
            pass

    # Terracotta motif bottom-right - subtle brand accent from the reference deck.
    if os.path.exists(MOTIF_PATH):
        try:
            motif_w = Inches(4.6)
            slide.shapes.add_picture(
                MOTIF_PATH,
                left=slide_w - motif_w + Inches(0.25),
                top=slide_h - Inches(3.4),
                width=motif_w,
            )
        except Exception:
            pass

    # Bottom-left: confidential footer, small dark green text.
    footer_h = Inches(0.35)
    tb = slide.shapes.add_textbox(Inches(0.45), slide_h - footer_h - Inches(0.15),
                                  Inches(8), footer_h)
    tf = tb.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = "INFORMATION IN THIS DOCUMENT IS PRIVATE AND CONFIDENTIAL"
    r.font.size = Pt(9)
    r.font.bold = False
    r.font.color.rgb = RGBColor(0x21, 0x36, 0x2B)

    # Bottom-right: slide number (or blank if unset).
    if slide_number is not None:
        tb = slide.shapes.add_textbox(slide_w - Inches(0.85), slide_h - footer_h - Inches(0.15),
                                      Inches(0.5), footer_h)
        tf = tb.text_frame
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        p = tf.paragraphs[0]
        r = p.add_run()
        r.text = str(slide_number)
        r.font.size = Pt(9)
        r.font.color.rgb = RGBColor(0x21, 0x36, 0x2B)


def _pptx_table_no_grid(table):
    """Kill PowerPoint's default table chrome (banding + the vertical gridlines):
    swap the table style to the built-in 'No Style, No Grid' and disable banding."""
    from pptx.oxml.ns import qn
    tbl_el = table._tbl
    tblPr = tbl_el.tblPr
    tblPr.set("bandRow", "0")
    tblPr.set("firstRow", "0")
    for el in tblPr.findall(qn("a:tableStyleId")):
        tblPr.remove(el)
    style_el = tblPr.makeelement(qn("a:tableStyleId"), {})
    style_el.text = "{5940675A-B579-460E-94D1-54222C63F5DA}"  # No Style, No Grid
    tblPr.append(style_el)


def _pptx_cell_no_vlines(cell):
    """Belt-and-braces: explicit no-fill left/right borders so no theme can draw verticals."""
    from pptx.oxml.ns import qn
    tcPr = cell._tc.get_or_add_tcPr()
    for tag in ("a:lnR", "a:lnL"):   # insert lnL last so final order is lnL, lnR (schema order)
        for el in tcPr.findall(qn(tag)):
            tcPr.remove(el)
        ln = tcPr.makeelement(qn(tag), {"w": "0"})
        ln.append(tcPr.makeelement(qn("a:noFill"), {}))
        tcPr.insert(0, ln)


def _build_scorecard_pptx(title, sel_label, win_hdrs, grid) -> bytes:
    """Native-PowerPoint slide with a wide table matching the on-screen scorecard.
    Editable in PowerPoint (not an image). Widescreen 16:9 layout with NAMAA brand chrome."""
    from io import BytesIO
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank

    # Paint NAMAA background + logo + motif + footer FIRST so the table renders on top.
    _brand_slide(slide, prs, slide_number=11)

    # Slide title (dark green, right of the logo).
    tb = slide.shapes.add_textbox(Inches(2.0), Inches(0.4), Inches(11.0), Inches(0.55))
    tf = tb.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = f"{title}  —  {sel_label}"
    r.font.size = Pt(20)
    r.font.bold = True
    r.font.color.rgb = RGBColor(0x21, 0x36, 0x2B)

    n_regions = len(SCORECARD_REGIONS)
    n_cols = 1 + n_regions * 4
    body_rows = [g for g in grid if not g.get("spacer")]
    n_rows = 2 + len(body_rows)
    left, top = Inches(0.35), Inches(1.15)
    width = Inches(12.7)
    height = Inches(0.55) + Inches(0.32) * len(body_rows)

    tbl_shape = slide.shapes.add_table(n_rows, n_cols, left, top, width, height)
    tbl = tbl_shape.table
    try:
        _pptx_table_no_grid(tbl)
    except Exception:
        pass

    label_w = Inches(1.7)
    remaining_in = 12.7 - 1.7
    per_region_in = remaining_in / n_regions
    month_in = per_region_in * 0.28
    mom_in = per_region_in - month_in * 3
    tbl.columns[0].width = label_w
    ci = 1
    for _ in SCORECARD_REGIONS:
        for _ in range(3):
            tbl.columns[ci].width = Inches(month_in)
            ci += 1
        tbl.columns[ci].width = Inches(mom_in)
        ci += 1

    # Row 0: region banner (merged across the 4 cols per region)
    tbl.cell(0, 0).text = ""
    _pptx_style_cell(tbl.cell(0, 0), size=10)
    for r_i, region in enumerate(SCORECARD_REGIONS):
        c0 = 1 + r_i * 4
        c1 = c0 + 3
        tbl.cell(0, c0).merge(tbl.cell(0, c1))
        tbl.cell(0, c0).text = SCORECARD_REGION_DISPLAY.get(region, region)
        _pptx_style_cell(tbl.cell(0, c0), bold=True, size=13, align="center",
                         color=(0x21, 0x36, 0x2B))

    # Row 1: month subheaders + MoM Δ, dark green banner
    tbl.cell(1, 0).text = ""
    _pptx_style_cell(tbl.cell(1, 0), size=9)
    ci = 1
    for _ in SCORECARD_REGIONS:
        for h in win_hdrs:
            tbl.cell(1, ci).text = h
            _pptx_style_cell(tbl.cell(1, ci), bold=True, size=10, align="center",
                             fill=(0x21, 0x36, 0x2B), color=(0xFF, 0xFF, 0xFF))
            ci += 1
        tbl.cell(1, ci).text = "MoM Δ"
        _pptx_style_cell(tbl.cell(1, ci), bold=True, size=10, align="center",
                         fill=(0x21, 0x36, 0x2B), color=(0xFF, 0xFF, 0xFF))
        ci += 1

    up_rgb = (0x16, 0xA3, 0x4A)
    dn_rgb = (0xB4, 0x47, 0x2E)
    flat_rgb = (0x64, 0x74, 0x8B)
    row_idx = 2
    for g in grid:
        if g.get("spacer"):
            continue
        tbl.cell(row_idx, 0).text = g["label"]
        _pptx_style_cell(tbl.cell(row_idx, 0), bold=True, size=10, align="left",
                         color=(0x21, 0x36, 0x2B))
        ci = 1
        for reg in g["regions"]:
            for v in reg["vals"]:
                tbl.cell(row_idx, ci).text = fmt(v, g["kind"]) if v is not None else "—"
                _pptx_style_cell(tbl.cell(row_idx, ci), size=10, align="right",
                                 color=(0x21, 0x36, 0x2B))
                if g.get("group_end"):
                    try:
                        _pptx_cell_bottom_border(tbl.cell(row_idx, ci))
                    except Exception:
                        pass
                ci += 1
            state = reg["state"]
            mom_txt = "—" if reg["mom"] is None else fmt(reg["mom"], g["kind"])
            tbl.cell(row_idx, ci).text = mom_txt
            mom_color = up_rgb if state == "up" else dn_rgb if state == "dn" else flat_rgb
            _pptx_style_cell(tbl.cell(row_idx, ci), bold=True, size=10, align="right",
                             color=mom_color)
            if g.get("group_end"):
                try:
                    _pptx_cell_bottom_border(tbl.cell(row_idx, ci))
                except Exception:
                    pass
            ci += 1
        row_idx += 1

    # Strip vertical borders on every cell (the group-end BOTTOM borders stay).
    try:
        for _r in range(n_rows):
            for _c in range(n_cols):
                _pptx_cell_no_vlines(tbl.cell(_r, _c))
    except Exception:
        pass

    buf = BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _render_all_hands_scorecard(df, all_months, metrics_spec, key_prefix, *, pptx_title=None):
    """Reproduce the Google Sheet All Hands scorecard layout: 4 region blocks side-by-side,
    each with the last 3 months (as-of picker) + a MoM Δ column, one row per metric.
    Negative MoM in red / positive in green (unless up_is_good=False, then flipped)."""
    if df is None or df.empty or not all_months:
        st.info("No panel data available.")
        return

    # As-of month picker (newest first) + PPTX download side-by-side.
    month_labels = [pd.Timestamp(m).strftime("%b %Y") for m in all_months]
    labels_desc = list(reversed(month_labels))
    picker_col, dl_col = st.columns([3, 1], vertical_alignment="bottom")
    with picker_col:
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

    # Build the grid once - drives both the HTML render and the PPTX export.
    grid, df = _scorecard_cell_values(df, metrics_spec, win)

    # Download-as-PowerPoint button.
    with dl_col:
        title_for_pptx = pptx_title or "All Hands"
        try:
            pptx_bytes = _build_scorecard_pptx(title_for_pptx, sel_label, win_hdrs, grid)
        except Exception as e:
            pptx_bytes = None
            st.caption(f"PPTX export unavailable: {type(e).__name__}")
        if pptx_bytes:
            fname_safe = title_for_pptx.replace(" ", "_")
            month_slug = sel_label.replace(" ", "_")
            st.download_button(
                "Download as slide",
                data=pptx_bytes,
                file_name=f"{fname_safe}_{month_slug}.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                key=f"{key_prefix}_scorecard_pptx",
                use_container_width=True,
            )

    # Build the HTML table for the on-screen render.
    n_regions = len(SCORECARD_REGIONS)
    total_cols = 1 + n_regions * 4
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

    html.append("<thead>")
    html.append("<tr>")
    html.append("<th class='sc-empty'></th>")
    for r in SCORECARD_REGIONS:
        html.append(f"<th class='sc-region' colspan='4'>{SCORECARD_REGION_DISPLAY.get(r, r)}</th>")
    html.append("</tr>")
    html.append("<tr>")
    html.append("<th class='sc-empty'></th>")
    for _ in SCORECARD_REGIONS:
        for h in win_hdrs:
            html.append(f"<th class='sc-month'>{h}</th>")
        html.append("<th class='sc-month'>MoM Δ</th>")
    html.append("</tr>")
    html.append("</thead><tbody>")

    state_to_cls = {"up": "sc-delta-up", "dn": "sc-delta-dn",
                    "flat": "sc-delta-flat", "na": "sc-delta-na"}
    for g in grid:
        if g.get("spacer"):
            html.append(f"<tr class='sc-spacer'><td colspan='{total_cols}'>&nbsp;</td></tr>")
            continue
        row_cls = "sc-group-end" if g.get("group_end") else ""
        html.append(f"<tr class='{row_cls}'>")
        html.append(f"<td class='sc-metric'>{g['label']}</td>")
        for reg in g["regions"]:
            for v in reg["vals"]:
                html.append(f"<td class='sc-val'>{fmt(v, g['kind']) if v is not None else '—'}</td>")
            mom_txt = "—" if reg["mom"] is None else fmt(reg["mom"], g["kind"])
            html.append(f"<td class='sc-delta {state_to_cls[reg['state']]}'>{mom_txt}</td>")
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
        /* Group-end rows get a thin bottom border under the value + MoM cells (like the sheet).
           The label cell is intentionally left borderless to keep the visual grouping clean. */
        table.scorecard tr.sc-group-end td.sc-val,
        table.scorecard tr.sc-group-end td.sc-delta {
            border-bottom: 1px solid #B7B0A0;
            padding-bottom: 8px;
        }
        table.scorecard tr.sc-spacer td { padding: 0; height: 10px; background: transparent; }
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

    # Click-to-filter: apply a pending country (from map / bar clicks) BEFORE the Market
    # picker widget is instantiated (Streamlit forbids changing a widget's state after).
    _pending = st.session_state.pop("_pending_cty", None)
    if _pending and _pending in disp:
        st.session_state["flt_cty"] = disp[_pending]

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
            # Refresh is a developer-only control (cache-buster); viewers get the 15-min cache.
            if _is_developer():
                try:
                    _refresh = st.button("Refresh", icon=":material/refresh:", use_container_width=True)
                except TypeError:
                    _refresh = st.button("Refresh", use_container_width=True)
                if _refresh:
                    load_bridge.clear()
                    st.rerun()
        period = _picker("Period", ["3M", "6M", "12M", "YTD", "All", "Custom"], "All", "flt_period")
        custom_rng = None
        if period == "Custom":
            _min_d = pd.Timestamp(all_months[0]).to_pydatetime().date().replace(day=1)
            _max_d = pd.Timestamp(all_months[-1]).to_pydatetime().date()
            try:
                _pop = st.popover("Pick dates")
            except Exception:
                _pop = st.container()
            with _pop:
                _cal = st.date_input("Custom range", value=(_min_d, _max_d),
                                     min_value=_min_d, max_value=_max_d, key="flt_custom_cal")
            if isinstance(_cal, (list, tuple)) and len(_cal) == 2 and all(_cal):
                custom_rng = _cal

    # Resolve the month window from the preset.
    if period == "Custom" and custom_rng:
        _c0 = pd.Timestamp(custom_rng[0]).replace(day=1)
        _c1 = pd.Timestamp(custom_rng[1]) + pd.offsets.MonthEnd(0)
        keep = [m for m in all_months if _c0 <= pd.Timestamp(m) <= _c1] or all_months
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
    # Delta base = the FIRST closed month in the selected window, so KPI deltas answer
    # "how did we move over the selected period" and visibly react to the timeline.
    # With a single closed month in view, fall back to plain month-over-month.
    _first_closed = int(closed_mask[closed_mask].index.min()) if closed_mask.any() else 0
    if _first_closed < closed_idx:
        base_row = d.iloc[_first_closed]
        delta_label = "vs " + str(base_row["month_label"])
    elif closed_idx > 0:
        base_row = d.iloc[closed_idx - 1]
        delta_label = "vs " + str(base_row["month_label"])
    else:
        base_row = None
        delta_label = "vs prior"

    st.markdown(
        '<div class="hdr">'
        f'<span class="badge">{sel_country}</span>'
        f'<span class="badge">{x[0]} - {x[-1]} &middot; {len(d)} months</span>'
        f'<span class="badge">KPIs as of {kpi_row["month_label"]} &middot; deltas {delta_label}</span></div>',
        unsafe_allow_html=True,
    )

    def kd(col_name):
        try:
            if base_row is None or col_name not in d.columns:
                return None
            return float(kpi_row[col_name]) - float(base_row[col_name])
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
            if base_row is not None:
                gp, np_ = float(base_row["gross_rr_usd"]), float(base_row["rr_after_mko_mfo_usd"])
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
        kpi_card(slot, label, fmt(kpi_row.get(col_name), kind), dv, dstr, kseries(col_name), up_good,
                 delta_label=delta_label)

    go = _go()

    # ---- Revenue ----
    def _top_market(col):
        """Country with the highest value of `col` at the KPI month (ME excluded)."""
        try:
            snapc = df[(df["month_end"] == kpi_row["month_end"]) & (df["country"] != "Middle East")]
            snapc = snapc.dropna(subset=[col])
            if snapc.empty:
                return None, None
            r0 = snapc.loc[snapc[col].astype(float).idxmax()]
            return r0["country"], float(r0[col])
        except Exception:
            return None, None

    sec("Revenue", "Recognized revenue flow and the occupied-kitchen revenue stock")
    _parts = []
    _nr, _dnr = kpi_row.get("nrra_usd"), kd("nrra_usd")
    if _nr is not None:
        _s = f"NRRA <b>{fmt(_nr, 'usd')}</b> in {kpi_row['month_label']}"
        if _dnr is not None:
            _s += f" ({'+' if _dnr >= 0 else '-'}{fmt(abs(_dnr), 'usd')} {delta_label})"
        _parts.append(_s)
    _tc, _tv = _top_market("nrra_usd")
    if _tc:
        _parts.append(f"top market: <b>{_tc}</b> ({fmt(_tv, 'usd')})")
    if conc_now is not None:
        _parts.append(f"concession load <b>{conc_now * 100:.1f}%</b> of gross RR")
    if _parts:
        insight(" &middot; ".join(_parts))
    c1, c2 = st.columns(2)
    with c1:
        fig = go.Figure()
        for lbl, cn, color in [("RRA $", "rra_usd", TEAL), ("RRL $", "rrl_usd", RED),
                               ("NRRA $", "nrra_usd", NAVY)]:
            if cn in d.columns:
                add_line(fig, x, d[cn].tolist(), lbl, color, closed_idx, fmt_kind="usd")
        money_axis(_base_layout(fig, "Recurring Revenue - added / lost / net"))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    with c2:
        fig = go.Figure()
        for lbl, cn, color in [("Gross RR $", "gross_rr_usd", NAVY),
                               ("RR after MKO/MFO $", "rr_after_mko_mfo_usd", ORANGE)]:
            if cn in d.columns:
                add_line(fig, x, d[cn].tolist(), lbl, color, closed_idx, fmt_kind="usd")
        money_axis(_base_layout(fig, "Occupied-kitchen revenue at EoP (gap = concessions)"))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ---- Sales & Churn ----
    sec("Sales &amp; Churn", "Deal flow vs attrition, and the contract value behind it")
    _parts = []
    _cw, _dcw = kpi_row.get("cws"), kd("cws")
    if _cw is not None:
        _s = f"<b>{fmt(_cw, 'num')}</b> CWs in {kpi_row['month_label']}"
        if _dcw is not None:
            _s += f" ({'+' if _dcw >= 0 else ''}{fmt(_dcw, 'num')} {delta_label})"
        _parts.append(_s)
    _tc, _tv = _top_market("cws")
    if _tc:
        _parts.append(f"most CWs: <b>{_tc}</b> ({fmt(_tv, 'num')})")
    _ch = kpi_row.get("churns_excl_transfers")
    _na = kpi_row.get("net_adds")
    if _ch is not None and _na is not None:
        _parts.append(f"churns {fmt(_ch, 'num')} &rarr; net adds <b>{fmt(_na, 'num')}</b>")
    if _parts:
        insight(" &middot; ".join(_parts))
    c3, c4 = st.columns(2)
    with c3:
        fig = go.Figure()
        if "cws" in d.columns:
            add_bar(fig, x, d["cws"].tolist(), "CWs", TEAL, closed_idx, fmt_kind="num")
        if "approved_deals" in d.columns:
            add_bar(fig, x, d["approved_deals"].tolist(), "Approved", NAVY, closed_idx, fmt_kind="num")
        if "churns_excl_transfers" in d.columns:
            add_bar(fig, x, d["churns_excl_transfers"].tolist(), "Churns", RED, closed_idx, fmt_kind="num")
        _base_layout(fig, "CWs vs Approved vs Churns")
        fig.update_layout(barmode="group")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    with c4:
        fig = go.Figure()
        if "tcv_usd" in d.columns:
            add_line(fig, x, d["tcv_usd"].tolist(), "TCV $", NAVY, closed_idx, fmt_kind="usd")
        if "approved_tcv_usd" in d.columns:
            add_line(fig, x, d["approved_tcv_usd"].tolist(), "Approved TCV $", ORANGE, closed_idx,
                     fmt_kind="usd")
        money_axis(_base_layout(fig, "TCV vs Approved TCV"))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ---- Mix (stacked distributions) ----
    sec("Mix", "Who the revenue comes from and how long the contracts run")
    _parts = []
    _segs = [("Start-ups", "rr_pct_startups"), ("Independents", "rr_pct_independents"),
             ("Growth", "rr_pct_growth"), ("Enterprise", "rr_pct_enterprise")]
    try:
        _seg_vals = [(lbl, float(kpi_row[cn])) for lbl, cn in _segs
                     if cn in d.columns and pd.notna(kpi_row.get(cn))]
        if _seg_vals:
            _bl, _bv = max(_seg_vals, key=lambda t: t[1])
            _parts.append(f"<b>{_bl}</b> hold {_bv * 100:.0f}% of recurring revenue")
    except Exception:
        pass
    try:
        _terms = [("&lt;= 6m", "cw_term_lte_6m"), ("7-12m", "cw_term_7_12m"),
                  ("13-18m", "cw_term_13_18m"), ("19-24m", "cw_term_19_24m"),
                  ("25-36m", "cw_term_25_36m"), ("&gt; 36m", "cw_term_gt_36m")]
        _term_vals = [(lbl, float(kpi_row[cn])) for lbl, cn in _terms
                      if cn in d.columns and pd.notna(kpi_row.get(cn))]
        if _term_vals:
            _tl, _tvv = max(_term_vals, key=lambda t: t[1])
            _parts.append(f"most common CW term: <b>{_tl}</b> ({_tvv * 100:.0f}% of wins)")
    except Exception:
        pass
    if _parts:
        insight(" &middot; ".join(_parts) + f" &middot; as of {kpi_row['month_label']}")
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
    sec("Countries", "Click a bubble on the map or a bar to focus the whole dashboard on that market")
    labels = [l for (l, c, k) in COMPARE_METRICS if c in df.columns]
    default_lbl = "NRRA $ (net)" if "NRRA $ (net)" in labels else labels[0]
    sel_label = st.selectbox("Metric", labels, index=labels.index(default_lbl))
    sel_col, sel_kind = next((c, k) for (l, c, k) in COMPARE_METRICS if l == sel_label)

    dc = df[(df["month_end"].isin(keep_months)) & (df["country"] != "Middle East")].copy()
    dme = df[(df["month_end"].isin(keep_months)) & (df["country"] == "Middle East")].sort_values("month_end")

    # Leader / laggard takeaway for the chosen metric.
    try:
        _snapc = dc[dc["month_end"] == kpi_row["month_end"]].dropna(subset=[sel_col])
        if not _snapc.empty:
            _ld = _snapc.loc[_snapc[sel_col].astype(float).idxmax()]
            _lg = _snapc.loc[_snapc[sel_col].astype(float).idxmin()]
            _parts = [f"<b>{_ld['country']}</b> leads {sel_label} with {fmt(_ld[sel_col], sel_kind)}",
                      f"lowest: <b>{_lg['country']}</b> ({fmt(_lg[sel_col], sel_kind)})"]
            if sel_kind != "pct" and not dme.empty:
                _mesnap = dme[dme["month_end"] == kpi_row["month_end"]]
                if not _mesnap.empty and pd.notna(_mesnap[sel_col].iloc[0]) and float(_mesnap[sel_col].iloc[0]):
                    _parts.append(f"{_ld['country']} = "
                                  f"<b>{float(_ld[sel_col]) / float(_mesnap[sel_col].iloc[0]) * 100:.0f}%</b> of ME")
            insight(" &middot; ".join(_parts) + f" &middot; {kpi_row['month_label']}")
    except Exception:
        pass

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
                        hoverinfo="text", customdata=cts))
                    fig.update_layout(map=map_cfg)
                except (AttributeError, ValueError):
                    fig = go.Figure(go.Scattermapbox(
                        lat=lats, lon=lons, mode="markers+text", marker=mk, text=texts,
                        textposition="top center", textfont=dict(size=12, color="#21362B"),
                        hoverinfo="text", customdata=cts))
                    fig.update_layout(mapbox=map_cfg)
                fig.update_layout(
                    title=dict(text=f"{sel_label} - {_map_month} (click a bubble to focus)",
                               font=dict(size=14, color="#21362B", family="Arial Black, Arial")),
                    height=470, margin=dict(l=4, r=4, t=44, b=4), paper_bgcolor="white",
                    showlegend=False)
                fig.add_annotation(text="Powered by Esri", x=1, y=0, xref="paper", yref="paper",
                                   showarrow=False, xanchor="right", yanchor="bottom",
                                   font=dict(size=9, color="#7C776A"))
                _ev = _chart_with_select(fig, "map_sel",
                                         {"displayModeBar": False, "scrollZoom": True})
                _ck = _clicked_country(_ev) if _ev is not None else None
                if _ck and _ck != sel_country:
                    st.session_state["_pending_cty"] = _ck
                    st.rerun()
        except Exception as _map_err:
            st.info("Map unavailable: " + str(_map_err)[:160])
    with m2:
        snap = dc[dc["month_end"] == kpi_row["month_end"]].dropna(subset=[sel_col]).sort_values(sel_col)
        fig = go.Figure(go.Bar(
            x=snap[sel_col], y=snap["country"], orientation="h",
            marker_color=[COUNTRY_COLORS.get(c, SLATE) for c in snap["country"]],
            text=[fmt(v, sel_kind) for v in snap[sel_col]], textposition="outside",
            customdata=snap["country"].tolist(),
            hovertemplate="<b>%{customdata}</b>: %{text}<extra></extra>",
        ))
        _base_layout(fig, f"{sel_label} - {kpi_row['month_label']}", height=470)
        fig.update_xaxes(showticklabels=False)
        fig.update_layout(margin=dict(l=8, r=70, t=44, b=4))
        _ev2 = _chart_with_select(fig, "rank_sel", {"displayModeBar": False})
        _ck2 = _clicked_country(_ev2) if _ev2 is not None else None
        if _ck2 and _ck2 != sel_country:
            st.session_state["_pending_cty"] = _ck2
            st.rerun()

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
        _render_all_hands_scorecard(df, all_months, CK_SCORECARD_METRICS, "ck",
                                    pptx_title="ME All Hands - Cloud Kitchens")
    with tab_cr:
        _render_all_hands_scorecard(df, all_months, CR_SCORECARD_METRICS, "cr",
                                    pptx_title="ME All Hands - Cloud Retail")


main()
