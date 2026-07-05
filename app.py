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


@st.cache_data(show_spinner=False)
def _logo_b64() -> str:
    try:
        with open(LOGO_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")
    except Exception:
        return ""

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


# ---------------------------------------------------------------- main
def main():
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

    _b64 = _logo_b64()
    if _b64:
        st.markdown(
            '<div class="nm-banner"><img src="data:image/jpeg;base64,' + _b64 + '"/>'
            '<div><p class="nm-name">NAMAA</p><p class="nm-sub">ME Sales Panel</p></div></div>',
            unsafe_allow_html=True,
        )

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
        # Real tile map (Leaflet-style basemap, same look as the Talabat site): bubbles at each
        # market sized by the metric, animated month by month (press play / drag the slider).
        try:
            import plotly.express as px

            da = dc.dropna(subset=[sel_col]).copy()
            da = da.sort_values("month_end")
            da["lat"] = da["country"].map(lambda c: COUNTRY_CENTROID.get(c, (None, None))[0])
            da["lon"] = da["country"].map(lambda c: COUNTRY_CENTROID.get(c, (None, None))[1])
            da["size_v"] = da[sel_col].astype(float).abs() + 1e-9
            da["lbl"] = [f"{c}: {fmt(v, sel_kind)}" for c, v in zip(da["country"], da[sel_col])]
            kwargs = dict(
                lat="lat", lon="lon", size="size_v", color="country",
                color_discrete_map=COUNTRY_COLORS, text="lbl",
                hover_name="lbl", hover_data={"lat": False, "lon": False, "size_v": False,
                                              "country": False, "month_label": True},
                animation_frame="month_label", size_max=42,
                zoom=4.4, center={"lat": 26.0, "lon": 49.6}, height=480,
            )
            try:
                fig = px.scatter_map(da, map_style="carto-positron", **kwargs)
            except (AttributeError, TypeError):
                fig = px.scatter_mapbox(da, mapbox_style="carto-positron", **kwargs)
            fig.update_traces(textposition="top center",
                              textfont=dict(size=11, color="#21362B"))
            fig.update_layout(
                title=dict(text=f"{sel_label} - month by month (press play)",
                           font=dict(size=14, color="#21362B", family="Arial Black, Arial")),
                margin=dict(l=4, r=4, t=44, b=4), paper_bgcolor="white",
                legend=dict(orientation="h", y=-0.02, font=dict(size=11)),
            )
            # Start on the last closed month instead of the first frame.
            try:
                target = kpi_row["month_label"]
                for i, fr in enumerate(fig.frames):
                    if fr.name == target:
                        fig.layout.sliders[0].active = i
                        for tr_old, tr_new in zip(fig.data, fr.data):
                            tr_old.update(tr_new)
                        break
            except Exception:
                pass
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        except Exception:
            st.info("Map unavailable.")
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


main()
