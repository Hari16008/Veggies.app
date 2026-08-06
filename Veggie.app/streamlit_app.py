"""
streamlit_app.py
-----------------
Streamlit web app for the veggie ordering forecast.

Implements the store manager's order cycle:
  Basic order days  -> Wednesday, Thursday, Saturday
  Full order days    -> Monday, Friday
  No order           -> Tuesday, Sunday
  (see item_config.py to change the calendar or item lists)

  1. Log what's received (by weight, or by box for coriander/mint)
  2. Log wastage the same way
  3. current_stock = last received - (sales + wastage since then)
  4. Suggested order = previous week's sales for the day(s) this order
     covers - current_stock

Deployment entry point. Streamlit Community Cloud (and most PaaS deploy
targets) auto-detect a file named `streamlit_app.py` at the repo root as
the app to run, so this file is the canonical entry point for deployment.

Run locally:
    streamlit run streamlit_app.py

Deploy on Streamlit Community Cloud:
    1. Push this repo to GitHub (this file must be at the repo root, or
       set the "Main file path" in the Cloud UI to its path).
    2. Go to https://share.streamlit.io -> "New app" -> pick this repo/branch.
    3. Main file path: streamlit_app.py
    4. Make sure requirements.txt (streamlit, pandas) is committed alongside it.
"""

from __future__ import annotations

import os
from datetime import date

import pandas as pd
import streamlit as st

from item_config import ITEMS, ORDER_CALENDAR, order_days_available, order_type_for_day, items_for_order_day
from forecast_engine import forecast_order, load_history
from inventory_log import append_entries, read_log

# ---------------------------------------------------------------------
# Page config - must be the first Streamlit call
# ---------------------------------------------------------------------
st.set_page_config(page_title="Veggie Order Forecast", page_icon="🥬", layout="wide")

# ---------------------------------------------------------------------
# Styling - earthy produce-market palette instead of default theme
# ---------------------------------------------------------------------
st.markdown(
    """
    <style>
        .stApp { background-color: #FAF7F0; }
        h1, h2, h3 { color: #2F4B2F; }
        div[data-testid="stMetricValue"] { color: #4C7A3F; }
        .stButton>button {
            background-color: #4C7A3F; color: white; border-radius: 6px; border: none;
        }
        .stButton>button:hover { background-color: #3A5E30; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🥬 Weekly Veggie Order Forecast")
st.caption("Suggested order quantities based on last week's sales and current stock on hand.")

# Build paths relative to THIS FILE's location, not the process's current
# working directory. Streamlit Cloud (and some other hosts) don't always
# launch the app with the repo root as the cwd, so a plain relative path
# like "data/item_master.csv" can fail with FileNotFoundError even when
# the file is correctly committed to the repo.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
SAMPLE_HISTORY_CSV = os.path.join(DATA_DIR, "sample_sales_history.csv")
UPLOADED_HISTORY_CSV = os.path.join(DATA_DIR, "uploaded_history.csv")
ITEM_MASTER_CSV = os.path.join(DATA_DIR, "item_master.csv")
RECEIVING_LOG_CSV = os.path.join(DATA_DIR, "receiving_log.csv")
WASTAGE_LOG_CSV = os.path.join(DATA_DIR, "wastage_log.csv")


# ---------------------------------------------------------------------
# Cached data access - avoids re-reading/recomputing on every rerun
# ---------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _load_history_cached(csv_path: str, mtime: float) -> pd.DataFrame:
    """mtime is part of the cache key so edits/new uploads invalidate the cache."""
    return load_history(csv_path)


@st.cache_data(show_spinner=False)
def _load_item_master_cached(mtime: float) -> pd.DataFrame:
    return pd.read_csv(ITEM_MASTER_CSV)


def _forecast_order_fresh(
    order_day: str, csv_path: str, current_stock: dict, apply_buffer: bool, item_master: pd.DataFrame
) -> pd.DataFrame:
    # Not cached: receiving/wastage logs change every time someone logs an
    # entry, and cache keys on mtime would need every dependent file's mtime.
    # The forecast itself is cheap, so we just recompute on every rerun.
    return forecast_order(
        order_day,
        history_csv=csv_path,
        current_stock=current_stock,
        receiving_csv=RECEIVING_LOG_CSV,
        wastage_csv=WASTAGE_LOG_CSV,
        apply_safety_buffer=apply_buffer,
        item_master=item_master,
    )


def _safe_mtime(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


if not os.path.exists(ITEM_MASTER_CSV):
    st.error(
        f"Couldn't find `data/item_master.csv` next to streamlit_app.py "
        f"(looked in `{DATA_DIR}`). Make sure the `data/` folder with all "
        f"4 CSVs was pushed to GitHub and sits in the same folder as "
        f"streamlit_app.py, then reboot the app."
    )
    st.stop()

item_master = _load_item_master_cached(_safe_mtime(ITEM_MASTER_CSV))

# ---------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------
with st.sidebar:
    st.header("Order Settings")

    order_days = order_days_available()
    today_name = date.today().strftime("%A")
    default_index = order_days.index(today_name) if today_name in order_days else 0

    order_day = st.selectbox("Which order are you placing?", order_days, index=default_index)

    order_type = order_type_for_day(order_day)  # "full" or "basic"
    scope_items = items_for_order_day(order_day)
    scope_label = "Full order (Basic + Other veggies + Fruits)" if order_type == "full" else "Basic order only"
    st.info(f"**{order_day} -> {scope_label}**\n\n{len(scope_items)} items on this order.")

    apply_buffer = st.checkbox(
        "Apply each item's safety buffer %",
        value=False,
        help="Off by default to match the manager's formula exactly "
             "(previous week's sales - current stock). Turn on to pad "
             "the order using the buffer % in item_master.csv.",
    )

    st.divider()
    data_source = st.radio("Sales history source", ["Sample data (demo)", "Upload my own CSV"])

    history_csv = SAMPLE_HISTORY_CSV
    if data_source == "Upload my own CSV":
        uploaded = st.file_uploader("Upload sales history CSV (date, item, qty_sold)", type="csv")
        if uploaded is not None:
            try:
                os.makedirs(DATA_DIR, exist_ok=True)
                with open(UPLOADED_HISTORY_CSV, "wb") as f:
                    f.write(uploaded.getbuffer())
                history_csv = UPLOADED_HISTORY_CSV
                st.success("Using your uploaded data.")
            except OSError as e:
                st.error(f"Couldn't save the uploaded file: {e}")
        else:
            st.warning("No file uploaded yet - showing sample data below.")

    st.divider()
    st.caption(
        "Order cycle: log what's received -> log wastage -> app computes "
        "current stock -> suggested order = last week's sales for the "
        "day(s) this order covers, minus current stock."
    )

if not os.path.exists(history_csv):
    st.error("No sales history found. Upload a CSV or use the sample data option in the sidebar.")
    st.stop()

# ---------------------------------------------------------------------
# Tabs: Receiving & Wastage logging, then the Order recommendation
# ---------------------------------------------------------------------
tab_order, tab_receive, tab_waste, tab_history = st.tabs(
    ["📋 Suggested Order", "📥 Log Receiving", "🗑️ Log Wastage", "📈 Sales History"]
)

# ---- Log Receiving ----
with tab_receive:
    st.subheader("Log what was received today")
    st.caption("Enter quantity by weight (kg), or box count for Coriander/Mint. Leave items at 0 to skip them.")
    recv_scope = st.radio("Items to log", ["Today's order items only", "All items"], key="recv_scope", horizontal=True)
    recv_items = scope_items if recv_scope == "Today's order items only" else ITEMS
    recv_date = st.date_input("Date received", value=date.today(), key="recv_date")

    recv_df = pd.DataFrame({
        "item": list(recv_items.keys()),
        "unit": [recv_items[i]["unit"] for i in recv_items],
        "received_qty": [0.0] * len(recv_items),
    })
    recv_edited = st.data_editor(recv_df, hide_index=True, use_container_width=True, disabled=["item", "unit"], key="recv_editor")

    if st.button("Save receiving log", type="primary"):
        entries = dict(zip(recv_edited["item"], recv_edited["received_qty"]))
        n = append_entries(RECEIVING_LOG_CSV, "received_qty", recv_date, entries)
        if n:
            st.success(f"Logged receiving for {n} item(s) on {recv_date.isoformat()}.")
            st.rerun()
        else:
            st.warning("Nothing entered above 0 - nothing was logged.")

    with st.expander("View receiving log"):
        st.dataframe(read_log(RECEIVING_LOG_CSV, "received_qty"), hide_index=True, use_container_width=True)

# ---- Log Wastage ----
with tab_waste:
    st.subheader("Log wastage / spoilage")
    st.caption("Enter quantity by weight (kg), or box count for Coriander/Mint. Leave items at 0 to skip them.")
    waste_scope = st.radio("Items to log", ["Today's order items only", "All items"], key="waste_scope", horizontal=True)
    waste_items = scope_items if waste_scope == "Today's order items only" else ITEMS
    waste_date = st.date_input("Date wasted", value=date.today(), key="waste_date")

    waste_df = pd.DataFrame({
        "item": list(waste_items.keys()),
        "unit": [waste_items[i]["unit"] for i in waste_items],
        "wastage_qty": [0.0] * len(waste_items),
    })
    waste_edited = st.data_editor(waste_df, hide_index=True, use_container_width=True, disabled=["item", "unit"], key="waste_editor")

    if st.button("Save wastage log", type="primary"):
        entries = dict(zip(waste_edited["item"], waste_edited["wastage_qty"]))
        n = append_entries(WASTAGE_LOG_CSV, "wastage_qty", waste_date, entries)
        if n:
            st.success(f"Logged wastage for {n} item(s) on {waste_date.isoformat()}.")
            st.rerun()
        else:
            st.warning("Nothing entered above 0 - nothing was logged.")

    with st.expander("View wastage log"):
        st.dataframe(read_log(WASTAGE_LOG_CSV, "wastage_qty"), hide_index=True, use_container_width=True)

# ---- Suggested Order ----
with tab_order:
    st.subheader(f"Suggested order for {order_day} ({'Full' if order_type == 'full' else 'Basic'})")

    st.caption(
        "Current stock is auto-computed from your receiving and wastage logs "
        "(received - sales - wastage since the last delivery). If an item has "
        "no receiving log yet, enter its stock manually below to override."
    )
    with st.expander("✏️ Manually override current stock (optional)", expanded=False):
        manual_df = pd.DataFrame({
            "item": list(scope_items.keys()),
            "unit": [scope_items[i]["unit"] for i in scope_items],
            "manual_stock": [0.0] * len(scope_items),
        })
        manual_edited = st.data_editor(
            manual_df, hide_index=True, use_container_width=True, disabled=["item", "unit"], key="manual_stock_editor"
        )
        st.caption("Leave at 0 to use the auto-computed value from the receiving/wastage logs.")

    manual_stock = dict(zip(manual_edited["item"], manual_edited["manual_stock"]))

    try:
        forecast_df = _forecast_order_fresh(order_day, history_csv, manual_stock, apply_buffer, item_master)
    except Exception as e:  # noqa: BLE001 - surface any forecast error to the user, don't crash the app
        st.error(f"Couldn't generate a forecast: {e}")
        st.stop()

    if forecast_df.empty:
        st.warning("No items scheduled for this order day.")
    else:
        editable = forecast_df.rename(columns={
            "item": "Item",
            "category": "Category",
            "unit": "Unit",
            "coverage_days": "Covers (days)",
            "prev_week_sales": "Last Week's Sales",
            "current_stock": "Current Stock",
            "stock_source": "Stock Source",
            "suggested_order_qty": "Order Qty",
        })

        final_edit = st.data_editor(
            editable,
            hide_index=True,
            use_container_width=True,
            disabled=[
                "Item", "Category", "Unit", "Covers (days)",
                "Last Week's Sales", "Current Stock", "Stock Source",
            ],
            key="order_editor",
        )

        col1, col2, col3 = st.columns(3)
        col1.metric("Items on this order", len(final_edit))
        col2.metric("Total order (kg items)", round(final_edit.loc[final_edit["Unit"] == "kg", "Order Qty"].sum(), 1))
        col3.metric("Total order (box items)", int(final_edit.loc[final_edit["Unit"] == "box", "Order Qty"].sum()))

        st.divider()
        st.subheader("📋 Final order sheet")
        st.caption("Adjust any quantity above based on your judgment, then export this list to send to your supplier.")

        csv_export = final_edit[["Item", "Unit", "Order Qty"]].to_csv(index=False)
        st.download_button(
            label="⬇️ Download order sheet (CSV)",
            data=csv_export,
            file_name=f"order_{order_day.lower()}_{date.today().isoformat()}.csv",
            mime="text/csv",
        )

        st.dataframe(final_edit[["Item", "Unit", "Order Qty"]], hide_index=True, use_container_width=True)

# ---- Historical view ----
with tab_history:
    st.subheader("Raw sales history")
    try:
        hist = _load_history_cached(history_csv, _safe_mtime(history_csv))
        st.dataframe(hist.sort_values("date", ascending=False), use_container_width=True, height=400)
    except Exception as e:  # noqa: BLE001
        st.write(f"Couldn't load history: {e}")
