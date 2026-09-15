"""
ROMI Officer Portal — Streamlit Cloud app (PUBLIC, no login).

Officers:
  * select their SBU, enter Name + Enroll, and ADD campaigns (add-only).
  * view a READ-ONLY ROMI analysis (all SBUs, no other tabs).

Deploy to Streamlit Cloud with secrets: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY.
NOTE: metrics (F/G/H/J/pool) are computed on-premise (refresh.py) since the
DWH is office-only; freshly added campaigns show "pending" until refresh runs.
"""

import calendar
import datetime as dt

import streamlit as st
import pandas as pd

import romi_logic
import supabase_client as sc

st.set_page_config(page_title="ROMI — Officer Portal", layout="wide")

APP_VERSION = "1.1"

CATEGORIES = ["ATL", "Digital", "BTL", "Outdoor", "Gift & Printing",
              "Research", "Trade Incentive Offer", "Other"]


def month_bounds(ym):
    """'YYYY-MM' -> (first_day, last_day) of that month."""
    y, m = map(int, ym.split("-"))
    first = dt.date(y, m, 1)
    if m == 12:
        last = dt.date(y, 12, 31)
    else:
        last = dt.date(y, m + 1, 1) - dt.timedelta(days=1)
    return first, last


def fmt_money(v):
    if v is None:
        return "—"
    v = float(v)
    if abs(v) >= 1e7:
        return f"{v/1e7:,.2f} Cr"
    if abs(v) >= 1e5:
        return f"{v/1e5:,.2f} L"
    return f"{v:,.0f}"


def fmt_pct(v):
    return "—" if v is None else f"{float(v)*100:,.2f}%"


def fmt_romi(v):
    return "—" if v is None else f"{float(v):,.2f}x"


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300)
def load_sbus():
    return sc.fetch_sbus()


@st.cache_data(ttl=120)
def load_campaigns():
    return sc.fetch_campaigns()


def sbu_options(sbus):
    return {f"{s['code']} — {s['name']}": int(s["business_unit_id"]) for s in sbus}


sbus = load_sbus()
sbu_by_label = sbu_options(sbus)
label_by_id = {v: k for k, v in sbu_by_label.items()}


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("ROMI Officer Portal")
st.sidebar.caption(f"v{APP_VERSION}")
page = st.sidebar.radio("Navigate", ["Input Campaign", "ROMI Analysis"])


# ---------------------------------------------------------------------------
# PAGE: Input Campaign (add-only)
# ---------------------------------------------------------------------------
def previous_month(ym):
    """'YYYY-MM' -> 'YYYY-MM' of the prior month."""
    y, m = map(int, ym.split("-"))
    if m == 1:
        return f"{y - 1:04d}-12"
    return f"{y:04d}-{m - 1:02d}"


def _parse_date(v):
    if v is None:
        return None
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, str):
        try:
            return dt.date.fromisoformat(v[:10])
        except Exception:
            return None
    try:
        ts = pd.to_datetime(v)
        return None if pd.isna(ts) else ts.date()
    except Exception:
        return None


def _shift_month(d):
    """Shift a date one month forward, clamping the day to the target month."""
    d = _parse_date(d)
    if d is None:
        return None
    y, m = d.year, d.month
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    last = calendar.monthrange(ny, nm)[1]
    return dt.date(ny, nm, min(d.day, last))


def _empty_grid(mb_start, mb_end):
    return pd.DataFrame([{
        "Campaign Name": "",
        "Type": CATEGORIES[0],
        "Start Date": mb_start,
        "End Date": mb_end,
        "Expense (BDT)": 0.0,
    }])


def _last_month_df(bu_id, officer_enroll, officer_name):
    """Copy the officer's previous-month campaigns (name + type, dates shifted)."""
    prev = previous_month(romi_logic.current_month())
    campaigns = load_campaigns()
    mine = [c for c in campaigns
            if c.get("business_unit_id") == bu_id
            and c.get("report_month") == prev
            and c.get("officer_enroll")
            and str(c.get("officer_enroll")).strip() == str(officer_enroll).strip()]
    if not mine and officer_name:
        mine = [c for c in campaigns
                if c.get("business_unit_id") == bu_id
                and c.get("report_month") == prev
                and c.get("officer_name")
                and str(c.get("officer_name")).strip() == str(officer_name).strip()]
    if not mine:
        return None
    rows = []
    for c in mine:
        cat = c.get("category") if c.get("category") in CATEGORIES else CATEGORIES[0]
        rows.append({
            "Campaign Name": c.get("campaign_name") or "",
            "Type": cat,
            "Start Date": _shift_month(c.get("start_date")),
            "End Date": _shift_month(c.get("end_date")),
            "Expense (BDT)": 0.0,
        })
    return pd.DataFrame(rows)


GRID_COLUMN_CONFIG = {
    "Campaign Name": st.column_config.TextColumn("Campaign Name", width="large"),
    "Type": st.column_config.SelectboxColumn("Type", options=CATEGORIES, required=True, width="medium"),
    "Start Date": st.column_config.DateColumn("Start Date", format="YYYY-MM-DD", width="small"),
    "End Date": st.column_config.DateColumn("End Date", format="YYYY-MM-DD", width="small"),
    "Expense (BDT)": st.column_config.NumberColumn("Expense (BDT)", min_value=0.0, step=1000.0, width="medium"),
}


def page_input():
    if st.session_state.get("flash"):
        st.success(st.session_state.pop("flash"))

    st.title("Add Marketing Campaign")
    st.caption("Select your SBU, find your name to enroll, then add one or more "
               "campaigns in the grid below and submit them together.")

    # ---- 1. SBU ----
    sbu_label = st.selectbox("SBU *", list(sbu_by_label.keys()), key="sbu_sel")
    bu_id = sbu_by_label[sbu_label]

    # ---- 2. Find your name & enroll ----
    roster = sc.fetch_employees(bu_id)
    officer_name = ""
    officer_enroll = ""
    if roster:
        opts = [f"{e.get('employee_name', '')}  —  {e.get('enroll') or 'no code'}" for e in roster]
        opts = ["— I'm new / not in the list —"] + opts
        sel = st.selectbox("Find your name & enroll *", opts, key="name_sel")
        if sel == opts[0]:
            officer_name = st.text_input("Your name *", key="new_name")
            officer_enroll = st.text_input("Employee code (Enroll)", key="new_enroll")
        else:
            emp = roster[opts.index(sel) - 1]
            officer_name = emp.get("employee_name") or ""
            officer_enroll = emp.get("enroll") or ""
            st.success(f"Enrolled as **{officer_name}** ({officer_enroll or 'no code'})")
    else:
        st.info("No employee roster for this SBU yet. Enter your name below — it will "
                "be saved so you can pick it next time.")
        officer_name = st.text_input("Your name *", key="new_name2")
        officer_enroll = st.text_input("Employee code (Enroll)", key="new_enroll2")

    # ---- 3. Campaign grid ----
    report_month = romi_logic.current_month()
    mb_start, mb_end = month_bounds(report_month)
    st.caption(f"Reporting month: **{report_month}**")

    if st.button("Copy my last month's campaigns"):
        copied = _last_month_df(bu_id, officer_enroll, officer_name)
        if copied is None or copied.empty:
            st.warning("No campaigns found for you in the previous month.")
        else:
            st.session_state["editor_version"] = st.session_state.get("editor_version", 0) + 1
            st.session_state["editor_prefill"] = copied
            st.info(f"Loaded {len(copied)} campaign(s) from last month — edit and submit.")

    version = st.session_state.get("editor_version", 0)
    prefill = st.session_state.get("editor_prefill")
    initial = prefill if (prefill is not None and version > 0) else _empty_grid(mb_start, mb_end)

    edited = st.data_editor(
        initial,
        num_rows="dynamic",
        column_config=GRID_COLUMN_CONFIG,
        use_container_width=True,
        hide_index=True,
        key=f"editor_{version}",
    )

    if st.button("Submit all campaigns", type="primary", use_container_width=True):
        if not officer_name.strip():
            st.error("Please select or enter your name before submitting.")
        else:
            submitted_rows = [
                r for _, r in edited.iterrows()
                if str(r.get("Campaign Name") or "").strip()
            ]
            if not submitted_rows:
                st.warning("No campaigns entered — add at least one row with a campaign name.")
            else:
                try:
                    sc.upsert_employee({
                        "business_unit_id": bu_id,
                        "employee_name": officer_name.strip(),
                        "enroll": officer_enroll.strip() or None,
                    })
                except Exception:
                    pass

                inserted, errors = 0, []
                for r in submitted_rows:
                    name = str(r["Campaign Name"]).strip()
                    sd = _parse_date(r.get("Start Date"))
                    ed = _parse_date(r.get("End Date"))
                    raw = r.get("Expense (BDT)")
                    try:
                        exp = 0.0 if raw is None or pd.isna(raw) else float(raw)
                    except (TypeError, ValueError):
                        exp = 0.0
                    if sd is None or ed is None:
                        errors.append(f"'{name}': missing start/end date.")
                        continue
                    if sd > ed:
                        errors.append(f"'{name}': start date after end date.")
                        continue
                    row = {
                        "business_unit_id": bu_id,
                        "campaign_name": name,
                        "category": r.get("Type") or CATEGORIES[0],
                        "report_month": report_month,
                        "start_date": sd.isoformat(),
                        "end_date": ed.isoformat(),
                        "officer_name": officer_name.strip(),
                        "officer_enroll": officer_enroll.strip(),
                        "marketing_expense_total": exp,
                    }
                    try:
                        sc.insert_campaign(row)
                        inserted += 1
                    except Exception as e:
                        errors.append(f"'{name}': {e}")

                load_campaigns.clear()
                for e in errors:
                    st.error(e)
                if inserted:
                    st.session_state["flash"] = f"Added {inserted} campaign(s). Metrics appear after the next data refresh."
                    st.session_state["editor_prefill"] = None
                    st.session_state["editor_version"] = st.session_state.get("editor_version", 0) + 1
                    st.rerun()


# ---------------------------------------------------------------------------
# PAGE: ROMI Analysis (read-only, all SBUs)
# ---------------------------------------------------------------------------
def page_analysis():
    st.title("ROMI Analysis")
    st.caption("Read-only view of all SBUs' campaign ROI.")

    campaigns = load_campaigns()
    if not campaigns:
        st.info("No campaigns yet.")
        return

    rows = [romi_logic.compute_effective(c) for c in campaigns]

    # ---- Month selector (defaults to the latest reporting month) ----
    months = sorted({c.get("report_month") for c in campaigns if c.get("report_month")}, reverse=True)
    if months:
        cur = st.selectbox("Reporting Month", months, index=0)
    else:
        cur = romi_logic.current_month()
    rows = [r for r in rows if r.get("report_month") == cur]
    st.caption(f"Showing reporting month: **{cur}**")
    if not rows:
        st.info(f"No campaigns filed for {cur} yet.")
        return

    # ---- Per-campaign table ----
    df = pd.DataFrame(rows)

    # Format raw columns before renaming so display labels never break the code
    for col in ["actual_rev", "organic_rev", "sply_rev", "incr_rev",
                "actual_profit", "base_profit", "sply_profit", "incr_profit",
                "marketing_expense"]:
        if col in df.columns:
            df[col] = df[col].apply(fmt_money)
    if "gp_margin" in df.columns:
        df["gp_margin"] = df["gp_margin"].apply(fmt_pct)
    if "romi_top" in df.columns:
        df["romi_top"] = df["romi_top"].apply(fmt_romi)
    if "romi_bottom" in df.columns:
        df["romi_bottom"] = df["romi_bottom"].apply(fmt_romi)
    if "business_unit_id" in df.columns:
        df["business_unit_id"] = df["business_unit_id"].map(label_by_id)

    disp = df.rename(columns={k: v for k, v in romi_logic.COLUMN_ORDER})
    order = [v for _, v in romi_logic.COLUMN_ORDER if v in disp.columns]
    st.dataframe(disp[order], use_container_width=True, height=450)

    # ---- SBU-wise totals (for the current month) ----
    st.divider()
    st.subheader(f"SBU-wise Totals — {cur}")
    by_bu = {}
    for r in rows:
        by_bu.setdefault(r["business_unit_id"], []).append(r)

    tot_rows = []
    for bu_id, rws in by_bu.items():
        t = romi_logic.sbu_totals(rws)
        t["SBU"] = label_by_id.get(bu_id, str(bu_id))
        tot_rows.append(t)

    tot = pd.DataFrame(tot_rows)
    tot = tot.rename(columns={
        "n_campaigns": "Campaigns",
        "total_incr_rev": "Total Marketing Led Increment",
        "total_incr_profit": "Total Marketing Led Profit",
        "total_marketing": "Total Marketing Expense",
        "total_romi_top": "Total ROMI (Top Line)",
        "total_romi_bottom": "Total ROMI (Bottom Line)",
    })
    for col in ["Total Marketing Led Increment", "Total Marketing Led Profit", "Total Marketing Expense"]:
        tot[col] = tot[col].apply(fmt_money)
    tot["Total ROMI (Top Line)"] = tot["Total ROMI (Top Line)"].apply(fmt_romi)
    tot["Total ROMI (Bottom Line)"] = tot["Total ROMI (Bottom Line)"].apply(fmt_romi)

    cols = ["SBU", "Campaigns", "Total Marketing Led Increment", "Total Marketing Led Profit",
            "Total Marketing Expense", "Total ROMI (Top Line)", "Total ROMI (Bottom Line)"]
    st.dataframe(tot[cols], use_container_width=True)

    # ---- Branch mark vs actual (charts + hover table) ----
    st.divider()
    st.subheader("Branch Mark vs Actual")
    sbus_by_id = {int(s["business_unit_id"]): s for s in sbus}
    bm_rows = romi_logic.benchmark_rows(rows, sbus_by_id)
    if bm_rows:
        log_y = st.toggle("Log scale (recommended — makes the branch marks visible)", value=True)
        st.plotly_chart(romi_logic.benchmark_chart_fig(bm_rows, "top", log_y),
                        use_container_width=True)
        st.plotly_chart(romi_logic.benchmark_chart_fig(bm_rows, "bottom", log_y),
                        use_container_width=True)
        st.markdown(
            romi_logic.BRANCHMARK_CSS + romi_logic.branchmark_table_html(bm_rows),
            unsafe_allow_html=True,
        )

    # ---- Top performing campaigns / activities ----
    st.divider()
    st.subheader("Top Performing Campaigns")
    top = romi_logic.top_campaigns(rows, n=10)
    if top:
        td = pd.DataFrame([{
            "SBU": label_by_id.get(r["business_unit_id"], str(r["business_unit_id"])),
            "Campaign": r["campaign_name"],
            "Activity": r["category"],
            "Marketing Expense": r["marketing_expense"],
            "Marketing Led Increment": r["incr_rev"],
            "ROMI (Top Line)": r["romi_top"],
            "ROMI (Bottom Line)": r["romi_bottom"],
        } for r in top])
        td["Marketing Expense"] = td["Marketing Expense"].apply(fmt_money)
        td["Marketing Led Increment"] = td["Marketing Led Increment"].apply(fmt_money)
        td["ROMI (Top Line)"] = td["ROMI (Top Line)"].apply(fmt_romi)
        td["ROMI (Bottom Line)"] = td["ROMI (Bottom Line)"].apply(fmt_romi)
        st.dataframe(td, use_container_width=True)
    else:
        st.info("No campaigns with computable ROMI yet.")


if page == "Input Campaign":
    page_input()
else:
    page_analysis()
