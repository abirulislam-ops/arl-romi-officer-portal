"""
ROMI Officer Portal — Streamlit Cloud app (PUBLIC, no login).

Officers:
  * select their SBU, enter Name + Enroll, and ADD campaigns (add-only).
  * view a READ-ONLY ROMI analysis (all SBUs, no other tabs).

Deploy to Streamlit Cloud with secrets: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY.
NOTE: metrics (F/G/H/J/pool) are computed on-premise (refresh.py) since the
DWH is office-only; freshly added campaigns show "pending" until refresh runs.
"""

import datetime as dt

import streamlit as st
import pandas as pd

import romi_logic
import supabase_client as sc

st.set_page_config(page_title="ROMI — Officer Portal", layout="wide")

CATEGORIES = ["ATL", "BTL", "Other"]


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
page = st.sidebar.radio("Navigate", ["Input Campaign", "ROMI Analysis"])


# ---------------------------------------------------------------------------
# PAGE: Input Campaign (add-only)
# ---------------------------------------------------------------------------
def page_input():
    st.title("Add Marketing Campaign")
    st.caption("Enter your campaign details. You can add as many campaigns as "
               "you ran this month. (No edit/delete here — contact SPA for corrections.)")

    with st.form("campaign_form", clear_on_submit=True):
        sbu_label = st.selectbox("SBU *", list(sbu_by_label.keys()))
        c1, c2 = st.columns(2)
        with c1:
            officer_name = st.text_input("Your Name *")
        with c2:
            officer_enroll = st.text_input("Employee Code (Enroll) *")

        campaign_name = st.text_input("Activity / Campaign Name *")
        category = st.selectbox("Campaign Category", CATEGORIES)

        report_month = romi_logic.current_month()
        mb_start, mb_end = month_bounds(report_month)
        st.caption(f"Reporting Month: **{report_month}** (current month — "
                   f"campaigns are filed for the current month only)")

        d1, d2 = st.columns(2)
        with d1:
            start_date = st.date_input("Start Date *", mb_start)
        with d2:
            end_date = st.date_input("End Date *", mb_end)

        marketing_expense = st.number_input(
            "Marketing Expense — monthly (BDT)",
            min_value=0.0, value=0.0, step=1000.0, format="%.0f",
            help="The campaign's marketing spend expressed per month. "
                 "SPA will reconcile this against the ledger.",
        )

        submitted = st.form_submit_button("Add Campaign", use_container_width=True)

    if submitted:
        errors = []
        if not campaign_name.strip():
            errors.append("Campaign name is required.")
        if not officer_name.strip():
            errors.append("Name is required.")
        if not officer_enroll.strip():
            errors.append("Employee code is required.")
        if start_date > end_date:
            errors.append("Start date must be on or before end date.")

        if errors:
            for e in errors:
                st.error(e)
        else:
            row = {
                "business_unit_id": sbu_by_label[sbu_label],
                "campaign_name": campaign_name.strip(),
                "category": category,
                "report_month": report_month,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "officer_name": officer_name.strip(),
                "officer_enroll": officer_enroll.strip(),
                "marketing_expense_monthly": float(marketing_expense),
            }
            try:
                sc.insert_campaign(row)
                load_campaigns.clear()
                st.success("Campaign added. Metrics (actual/organic/SPLY revenue, "
                           "GP margin) will appear after the next data refresh.")
            except Exception as e:
                st.error(f"Could not save: {e}")


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

    # ---- Current month only (officers see the current reporting month) ----
    cur = romi_logic.current_month()
    rows = [r for r in rows if r.get("report_month") == cur]
    st.caption(f"Showing the current month: **{cur}**")
    if not rows:
        st.info(f"No campaigns filed for {cur} yet.")
        return

    # ---- Per-campaign table ----
    df = pd.DataFrame(rows)
    disp = df.rename(columns={k: v for k, v in romi_logic.COLUMN_ORDER})
    disp["SBU"] = disp["SBU"].map(label_by_id)
    disp["GP Margin (%)"] = disp["GP Margin (%)"].apply(fmt_pct)
    disp["Actual Revenue (avg)"] = disp["Actual Revenue (avg)"].apply(fmt_money)
    disp["Organic/Base Sales (6-mo avg)"] = disp["Organic/Base Sales (6-mo avg)"].apply(fmt_money)
    disp["SPLY Revenue (avg)"] = disp["SPLY Revenue (avg)"].apply(fmt_money)
    disp["Incremental Revenue"] = disp["Incremental Revenue"].apply(fmt_money)
    disp["Actual Profit"] = disp["Actual Profit"].apply(fmt_money)
    disp["Base Profit"] = disp["Base Profit"].apply(fmt_money)
    disp["SPLY Profit"] = disp["SPLY Profit"].apply(fmt_money)
    disp["Incremental Profit"] = disp["Incremental Profit"].apply(fmt_money)
    disp["Marketing Expense (monthly)"] = disp["Marketing Expense (monthly)"].apply(fmt_money)
    disp["ROMI (Top Line)"] = disp["ROMI (Top Line)"].apply(fmt_romi)
    disp["ROMI (Bottom Line)"] = disp["ROMI (Bottom Line)"].apply(fmt_romi)

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
        "total_incr_rev": "Total Incremental Revenue",
        "total_incr_profit": "Total Incremental Profit",
        "total_marketing": "Total Marketing Expense",
        "total_romi_top": "Total ROMI (Top Line)",
        "total_romi_bottom": "Total ROMI (Bottom Line)",
    })
    for col in ["Total Incremental Revenue", "Total Incremental Profit", "Total Marketing Expense"]:
        tot[col] = tot[col].apply(fmt_money)
    tot["Total ROMI (Top Line)"] = tot["Total ROMI (Top Line)"].apply(fmt_romi)
    tot["Total ROMI (Bottom Line)"] = tot["Total ROMI (Bottom Line)"].apply(fmt_romi)

    cols = ["SBU", "Campaigns", "Total Incremental Revenue", "Total Incremental Profit",
            "Total Marketing Expense", "Total ROMI (Top Line)", "Total ROMI (Bottom Line)"]
    st.dataframe(tot[cols], use_container_width=True)


if page == "Input Campaign":
    page_input()
else:
    page_analysis()
