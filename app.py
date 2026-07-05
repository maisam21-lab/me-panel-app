"""ME Sales Panel - standalone Streamlit app (Tableau-style dashboard).

Reads the BigQuery bridge table that also feeds the Google Sheets panel
(css-operations.me_panel_dev_us.me_sales_panel_k_monthly), so both surfaces
always show the same numbers. Tabs: Dashboard / Countries / Panel.

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

TEAL = "#0F766E"
BLUE = "#2563EB"
RED = "#DC2626"
PURPLE = "#7C3AED"
AMBER = "#F59E0B"
SLATE = "#94A3B8"
GREEN = "#16A34A"

st.set_page_config(page_title="ME Sales Panel", layout="wide", page_icon=":bar_chart:",
                   initial_sidebar_state="collapsed")

st.markdown(
    """
    <style>
    .stApp { background: #F6F8FA; }
    #MainMenu, footer { visibility: hidden; }
    .block-container { padding-top: 1.2rem; max-width: 1500px; }
    /* Header bar */
    .hdr { display: flex; align-items: baseline; gap: 14px; margin-bottom: 4px; }
    .hdr .t { font-size: 1.45rem; font-weight: 800; color: #0B3B37; letter-spacing: -0.02em; }
    .hdr .badge { background: #E6F4F1; color: #0F766E; font-size: 0.75rem; font-weight: 700;
                  padding: 3px 10px; border-radius: 999px; }
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] { gap: 6px; background: transparent; padding: 4px 0; }
    .stTabs [data-baseweb="tab"] { padding: 8px 18px; border-radius: 8px; font-weight: 600; color: #475569;
                                   background: #EDF1F5; }
    .stTabs [aria-selected="true"] { background: #0F766E !important; color: white !important; }
    .stTabs [aria-selected="true"] p { color: white !important; }
    /* KPI cards via st.container(border=True) */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: #FFFFFF; border: 1px solid #E6EAF0 !important; border-radius: 14px;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
    }
    .kpi-l { font-size: 0.72rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
             color: #64748B; margin: 0; }
    .kpi-v { font-size: 1.55rem; font-weight: 800; color: #0F172A; margin: 2px 0 0 0; line-height: 1.1; }
    .kpi-d-up { color: #16A34A; font-size: 0.78rem; font-weight: 700; }
    .kpi-d-dn { color: #DC2626; font-size: 0.78rem; font-weight: 700; }
    .kpi-d-na { color: #94A3B8; font-size: 0.78rem; font-weight: 600; }
    .sec { font-size: 0.95rem; font-weight: 800; color: #0B3B37; text-transform: uppercase;
           letter-spacing: 0.05em; margin: 18px 0 2px 0; }
    .stDataFrame thead th { background: #F1F5F9 !important; font-weight: 600 !important; }
    /* No sidebar: all filters live in the top bar */
    section[data-testid="stSidebar"], [data-testid="collapsedControl"] { display: none !important; }
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
            pass  # invalid/placeholder SA -> fall through to ADC
    return bigquery.Client(project=BQ_PROJECT)  # Application Default Credentials


@st.cache_data(ttl=900, show_spinner="Loading panel data from BigQuery...")
def load_bridge() -> pd.DataFrame:
    """Pull the bridge (one row per country x month). Cached 15 min; the table rebuilds every 12h.

    Path 1: SQL query (needs bigquery.jobs.create). Path 2 fallback: direct table read via
    list_rows (needs ONLY dataset-level read - used by the deployed service account).
    """
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


# ---------------------------------------------------------------- formatting
def fmt(v, kind):
    try:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return ""
        if kind == "usd":
            return f"${float(v):,.0f}"
        if kind == "usd2":
            return f"${float(v):,.2f}"
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


# (label, bridge column, format). Section headers have col=None. Missing columns are skipped.
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

# Metrics offered in the Countries comparison tab (numeric only).
COMPARE_METRICS = [(l, c, k) for (l, c, k) in METRICS if c is not None]


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
    st.markdown('<div class="hdr"><span class="t">ME Sales Panel</span></div>', unsafe_allow_html=True)
    st.write("Enter your work email to open the panel.")
    email = st.text_input("Email", key="me_email_input")
    if st.button("Open", type="primary"):
        if email.strip().lower() in allowed:
            st.session_state["me_user_email"] = email.strip()
            st.rerun()
        else:
            st.error("This email is not on the allowed list. Ask Maysam to add you.")
    st.stop()


# ---------------------------------------------------------------- chart helpers
def _go():
    import plotly.graph_objects as go
    return go


def _base_layout(fig, title, height=330):
    fig.update_layout(
        title=dict(text=title, font=dict(size=14, color="#0B3B37", family="Arial Black, Arial")),
        height=height,
        margin=dict(l=8, r=8, t=42, b=4),
        legend=dict(orientation="h", y=-0.22, font=dict(size=11)),
        plot_bgcolor="white",
        paper_bgcolor="white",
        hovermode="x unified",
        font=dict(family="Arial", size=11, color="#334155"),
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#EEF2F6", zerolinecolor="#E2E8F0")
    return fig


def add_series(fig, x, y, name, color, closed_idx, is_bar=False):
    """Add a series; the stretch AFTER the last closed month renders dotted/translucent
    (partial live month - deliberately visually distinct)."""
    go = _go()
    if is_bar:
        colors = [color if i <= closed_idx else "rgba(148,163,184,0.45)" for i in range(len(x))]
        fig.add_trace(go.Bar(x=x, y=y, name=name, marker_color=colors))
        return
    solid_end = min(closed_idx, len(x) - 1)
    fig.add_trace(go.Scatter(x=x[: solid_end + 1], y=y[: solid_end + 1], mode="lines+markers",
                             name=name, line=dict(color=color, width=2.4), marker=dict(size=5)))
    if solid_end < len(x) - 1:
        fig.add_trace(go.Scatter(x=x[solid_end:], y=y[solid_end:], mode="lines+markers", name=name,
                                 line=dict(color=color, width=2, dash="dot"), marker=dict(size=5),
                                 opacity=0.55, showlegend=False, hoverinfo="skip"))


def money_axis(fig):
    fig.update_yaxes(tickprefix="$", tickformat="~s")
    return fig


def pct_axis(fig):
    fig.update_yaxes(tickformat=".0%")
    return fig


def spark(series, color=TEAL, height=56):
    go = _go()
    fig = go.Figure(go.Scatter(y=list(series), mode="lines",
                               line=dict(color=color, width=2),
                               fill="tozeroy", fillcolor="rgba(15,118,110,0.10)"))
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=2, b=0),
                      plot_bgcolor="white", paper_bgcolor="white", showlegend=False)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


COUNTRY_ISO = {"Saudi Arabia": "SAU", "UAE": "ARE", "Kuwait": "KWT", "Bahrain": "BHR", "Qatar": "QAT"}
COUNTRY_CENTROID = {  # (lat, lon) for the value labels; Bahrain nudged off Qatar
    "Saudi Arabia": (24.0, 44.5), "UAE": (23.6, 54.2), "Kuwait": (29.6, 47.6),
    "Bahrain": (26.9, 50.4), "Qatar": (24.9, 51.2),
}


def country_map(snap_df, sel_col, sel_kind, title):
    """Gulf choropleth: countries shaded by the metric, value labeled on each country."""
    go = _go()
    dd = snap_df[snap_df["country"].isin(COUNTRY_ISO)].dropna(subset=[sel_col]).copy()
    fig = go.Figure(go.Choropleth(
        locations=[COUNTRY_ISO[c] for c in dd["country"]],
        z=dd[sel_col].astype(float),
        colorscale=[[0.0, "#DDEEEB"], [1.0, "#0F766E"]],
        marker_line_color="white", marker_line_width=1.4,
        showscale=False,
        hovertext=[f"{c}: {fmt(v, sel_kind)}" for c, v in zip(dd["country"], dd[sel_col])],
        hoverinfo="text",
    ))
    fig.add_trace(go.Scattergeo(
        lat=[COUNTRY_CENTROID[c][0] for c in dd["country"]],
        lon=[COUNTRY_CENTROID[c][1] for c in dd["country"]],
        text=[f"<b>{c}</b><br>{fmt(v, sel_kind)}" for c, v in zip(dd["country"], dd[sel_col])],
        mode="text", textfont=dict(size=13, color="#0B3B37"),
        hoverinfo="skip", showlegend=False,
    ))
    fig.update_geos(fitbounds="locations", visible=False, bgcolor="white",
                    showcountries=True, countrycolor="#E2E8F0",
                    showland=True, landcolor="#F8FAFC")
    fig.update_layout(
        title=dict(text=title, font=dict(size=14, color="#0B3B37", family="Arial Black, Arial")),
        height=460, margin=dict(l=4, r=4, t=42, b=4), paper_bgcolor="white",
    )
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
                st.markdown(f'<span class="{cls}">{arrow} {delta_str} vs prior month</span>',
                            unsafe_allow_html=True)
            if series is not None and len(series) > 1:
                st.plotly_chart(spark(series), use_container_width=True,
                                config={"displayModeBar": False, "staticPlot": True})


# ---------------------------------------------------------------- main
def main():
    _access_gate()

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

    df["month_label"] = df["month_end"].dt.strftime("%b %Y")
    all_months = sorted(df["month_end"].unique())
    all_labels = [pd.Timestamp(m).strftime("%b %Y") for m in all_months]
    cur_month_start = pd.Timestamp.today().normalize().replace(day=1)

    # ---- top filter bar (no sidebar) ----
    st.markdown('<div class="hdr"><span class="t">ME Sales Panel</span></div>', unsafe_allow_html=True)
    with st.container(border=True):
        f1, f2, f3 = st.columns([1.3, 3.2, 0.8], vertical_alignment="bottom")
        with f1:
            countries = [c for c in COUNTRIES if c in set(df["country"])]
            sel_country = st.selectbox(
                "Country", countries, index=0,
                help="Source: " + BRIDGE_TABLE + " - rebuilt every 12h; same bridge the Google "
                     "Sheets panel reads. Recognized revenue matures over ~2 months; the current "
                     "(partial) month is dotted/grey on charts and excluded from headline KPIs.",
            )
        with f2:
            if len(all_labels) > 1:
                rng = st.select_slider("Months", options=all_labels,
                                       value=(all_labels[0], all_labels[-1]))
            else:
                rng = (all_labels[0], all_labels[-1])
        with f3:
            if st.button("Refresh", use_container_width=True):
                load_bridge.clear()
                st.rerun()

    i0, i1 = all_labels.index(rng[0]), all_labels.index(rng[1])
    if i0 > i1:
        i0, i1 = i1, i0
    keep_months = set(all_months[i0:i1 + 1])

    d = df[(df["country"] == sel_country) & (df["month_end"].isin(keep_months))]
    d = d.sort_values("month_end").reset_index(drop=True)
    if d.empty:
        st.info("No rows for this selection.")
        st.stop()
    x = d["month_label"].tolist()

    # Last CLOSED month index within the filtered window (partial live month excluded from KPIs).
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

    tab_dash, tab_cmp, tab_panel = st.tabs(["Dashboard", "Countries", "Panel"])

    # ------------------------------------------------------------ Dashboard
    with tab_dash:
        def kv(col_name):
            return kpi_row.get(col_name)

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

        KPIS = [
            ("CWs", "cws", "num", True),
            ("Approved Deals", "approved_deals", "num", True),
            ("New Occupied Kitchens", "new_occupied_k", "num", True),
            ("NRRA $", "nrra_usd", "usdk", True),
            ("Gross RR $ (EoP)", "gross_rr_usd", "usdk", True),
            ("RR after MKO/MFO $", "rr_after_mko_mfo_usd", "usdk", True),
            ("Occupancy", "occupancy", "pct", True),
            ("Live Sold Rate", "live_sold_rate", "pct", True),
        ]
        row1 = st.columns(4)
        row2 = st.columns(4)
        slots = row1 + row2
        for (label, col_name, kind, up_good), slot in zip(KPIS, slots):
            if col_name not in d.columns:
                continue
            dv = kd(col_name)
            if kind == "pct" and dv is not None:
                dstr = f"{dv * 100:+.1f} pp"
            else:
                dstr = fmt(abs(dv) if dv is not None else None, kind)
            kpi_card(slot, label, fmt(kv(col_name), kind), dv, dstr, kseries(col_name), up_good)

        go = _go()

        st.markdown('<p class="sec">Revenue</p>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            fig = go.Figure()
            for lbl, cn, color in [("RRA $", "rra_usd", TEAL), ("RRL $", "rrl_usd", RED),
                                   ("NRRA $", "nrra_usd", BLUE)]:
                if cn in d.columns:
                    add_series(fig, x, d[cn].tolist(), lbl, color, closed_idx)
            money_axis(_base_layout(fig, "Recurring Revenue (recognized) - added / lost / net"))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        with c2:
            fig = go.Figure()
            for lbl, cn, color in [("Gross RR $", "gross_rr_usd", TEAL),
                                   ("RR after MKO/MFO $", "rr_after_mko_mfo_usd", PURPLE)]:
                if cn in d.columns:
                    add_series(fig, x, d[cn].tolist(), lbl, color, closed_idx)
            money_axis(_base_layout(fig, "Occupied-kitchen revenue at EoP (gap = concession load)"))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        c3, c4 = st.columns(2)
        with c3:
            fig = go.Figure()
            if "tcv_usd" in d.columns:
                add_series(fig, x, d["tcv_usd"].tolist(), "TCV $", TEAL, closed_idx)
            if "approved_tcv_usd" in d.columns:
                add_series(fig, x, d["approved_tcv_usd"].tolist(), "Approved TCV $", AMBER, closed_idx)
            money_axis(_base_layout(fig, "TCV vs Approved TCV"))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        with c4:
            if {"gross_rr_usd", "rr_after_mko_mfo_usd"} <= set(d.columns):
                load_pct = [
                    (float(g) - float(n)) / float(g) if g else None
                    for g, n in zip(d["gross_rr_usd"], d["rr_after_mko_mfo_usd"])
                ]
                fig = go.Figure()
                add_series(fig, x, load_pct, "Concession load %", PURPLE, closed_idx)
                pct_axis(_base_layout(fig, "Concession load (discounts as % of gross RR)"))
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        st.markdown('<p class="sec">Sales &amp; Churn</p>', unsafe_allow_html=True)
        c5, c6 = st.columns(2)
        with c5:
            fig = go.Figure()
            if "cws" in d.columns:
                add_series(fig, x, d["cws"].tolist(), "CWs", TEAL, closed_idx, is_bar=True)
            if "approved_deals" in d.columns:
                add_series(fig, x, d["approved_deals"].tolist(), "Approved", SLATE, closed_idx, is_bar=True)
            _base_layout(fig, "CWs vs Approved Deals")
            fig.update_layout(barmode="group")
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        with c6:
            fig = go.Figure()
            if "churns_excl_transfers" in d.columns:
                add_series(fig, x, d["churns_excl_transfers"].tolist(), "Churns", RED, closed_idx, is_bar=True)
            if "net_adds" in d.columns:
                add_series(fig, x, d["net_adds"].tolist(), "Net Adds", TEAL, closed_idx)
            _base_layout(fig, "Churns vs Net Adds")
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        st.markdown('<p class="sec">Occupancy</p>', unsafe_allow_html=True)
        c7, c8 = st.columns(2)
        with c7:
            fig = go.Figure()
            for lbl, cn, color in [("Occupancy", "occupancy", BLUE),
                                   ("Live Sold Rate", "live_sold_rate", TEAL),
                                   ("Live Sold Rate w/ Approved", "live_sold_rate_approved", AMBER)]:
                if cn in d.columns:
                    add_series(fig, x, d[cn].tolist(), lbl, color, closed_idx)
            pct_axis(_base_layout(fig, "Occupancy vs Live Sold Rates"))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        with c8:
            fig = go.Figure()
            if "occupied_kitchens" in d.columns:
                add_series(fig, x, d["occupied_kitchens"].tolist(), "Occupied Kitchens", TEAL, closed_idx)
            if "total_kitchens" in d.columns:
                add_series(fig, x, d["total_kitchens"].tolist(), "Total Kitchen Numbers", SLATE, closed_idx)
            _base_layout(fig, "Occupied Kitchens vs TKN")
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ------------------------------------------------------------ Countries
    with tab_cmp:
        labels = [l for (l, c, k) in COMPARE_METRICS if c in df.columns]
        sel_label = st.selectbox("Metric", labels,
                                 index=labels.index("NRRA $ (net)") if "NRRA $ (net)" in labels else 0)
        sel_col, sel_kind = next((c, k) for (l, c, k) in COMPARE_METRICS if l == sel_label)

        dc = df[(df["month_end"].isin(keep_months)) & (df["country"] != "Middle East")]
        dme = df[(df["month_end"].isin(keep_months)) & (df["country"] == "Middle East")].sort_values("month_end")

        # Map hero: metric across the Gulf at the last closed month
        snap_map = dc[dc["month_end"] == kpi_row["month_end"]]
        if not snap_map.empty and sel_col in snap_map.columns:
            st.plotly_chart(
                country_map(snap_map, sel_col, sel_kind,
                            f"{sel_label} - {kpi_row['month_label']}"),
                use_container_width=True, config={"displayModeBar": False},
            )

        go = _go()
        b1, b2 = st.columns([2, 3])
        with b1:
            snap = dc[dc["month_end"] == kpi_row["month_end"]].sort_values(sel_col, ascending=True)
            fig = go.Figure(go.Bar(
                x=snap[sel_col], y=snap["country"], orientation="h", marker_color=TEAL,
                text=[fmt(v, sel_kind) for v in snap[sel_col]], textposition="outside",
            ))
            _base_layout(fig, f"{sel_label} - {kpi_row['month_label']}", height=380)
            fig.update_xaxes(showticklabels=False)
            fig.update_layout(margin=dict(l=8, r=60, t=42, b=4))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        with b2:
            fig = go.Figure()
            colors = {"Saudi Arabia": TEAL, "UAE": BLUE, "Kuwait": AMBER, "Bahrain": PURPLE, "Qatar": SLATE}
            for cty in [c for c in COUNTRIES if c != "Middle East"]:
                dd = dc[dc["country"] == cty].sort_values("month_end")
                if not dd.empty and sel_col in dd.columns:
                    fig.add_trace(go.Scatter(x=dd["month_label"], y=dd[sel_col], mode="lines+markers",
                                             name=cty, line=dict(color=colors.get(cty, SLATE), width=2)))
            _base_layout(fig, f"{sel_label} - trend by country", height=380)
            if sel_kind in ("usd", "usd2", "usdk"):
                money_axis(fig)
            elif sel_kind == "pct":
                pct_axis(fig)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        # Ranked table: latest closed month + MoM + share of ME
        rows_out = []
        prev_month = d.iloc[closed_idx - 1]["month_end"] if closed_idx > 0 else None
        me_val = None
        if not dme.empty:
            me_snap = dme[dme["month_end"] == kpi_row["month_end"]]
            me_val = float(me_snap[sel_col].iloc[0]) if not me_snap.empty and sel_col in me_snap.columns else None
        for cty in [c for c in COUNTRIES if c != "Middle East"]:
            dd = dc[dc["country"] == cty]
            now_r = dd[dd["month_end"] == kpi_row["month_end"]]
            if now_r.empty or sel_col not in now_r.columns:
                continue
            now_v = float(now_r[sel_col].iloc[0]) if pd.notna(now_r[sel_col].iloc[0]) else None
            prev_v = None
            if prev_month is not None:
                pr = dd[dd["month_end"] == prev_month]
                if not pr.empty and pd.notna(pr[sel_col].iloc[0]):
                    prev_v = float(pr[sel_col].iloc[0])
            rows_out.append({
                "Country": cty,
                kpi_row["month_label"]: fmt(now_v, sel_kind),
                "MoM": fmt(now_v - prev_v, sel_kind) if (now_v is not None and prev_v is not None) else "",
                "Share of ME": fmt(now_v / me_val, "pct") if (me_val and now_v is not None and sel_kind != "pct") else "",
            })
        if rows_out:
            st.dataframe(pd.DataFrame(rows_out), use_container_width=True, hide_index=True)

    # ------------------------------------------------------------ Panel
    with tab_panel:
        months = x
        row_labels, table_rows = [], []
        for lbl, col_name, kind in METRICS:
            if col_name is None:
                row_labels.append("- " + lbl + " -")
                table_rows.append([""] * len(months))
            elif col_name in d.columns:
                row_labels.append(lbl)
                table_rows.append([fmt(v, kind) for v in d[col_name].tolist()])
        panel_df = pd.DataFrame(table_rows, index=row_labels, columns=months)
        st.dataframe(panel_df, use_container_width=True,
                     height=min(60 + 35 * len(row_labels), 1250))
        st.caption("Same bridge the Google Sheets panel reads - numbers match the sheet at its last extract pull.")


main()
