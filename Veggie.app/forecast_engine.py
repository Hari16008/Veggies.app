"""
forecast_engine.py
-------------------
Implements the store manager's order cycle:

  1. When veggies are received, take inventory BY WEIGHT (kg), except
     Coriander/Mint which are taken BY BOX.
  2. Capture wastage the same way (kg or box).
  3. current_stock = last_received_qty - (sales_since_receipt + wastage_since_receipt)
  4. new_order_qty  = previous_week_sales(for the day(s) this order must
                       cover, per item_config.coverage_weekdays)
                       - current_stock
     (floored at 0; box items are rounded up to a whole box)

Which items are on an order, and how many days that order needs to
cover, come from item_config.py (basic/full/none calendar).

Data sources (all plain CSVs so a shop PC / Streamlit Cloud can edit
them with no database):
  - history_csv    : date, item, qty_sold          (POS sales export)
  - receiving_csv  : date, item, received_qty      (logged when stock arrives)
  - wastage_csv     : date, item, wastage_qty       (logged as spoilage is pulled)
"""

from __future__ import annotations

import math
import pandas as pd

from item_config import ITEMS, items_for_order_day, coverage_weekdays


# ---------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------
def load_history(path: str) -> pd.DataFrame:
    """Load the sales history CSV: date, item, qty_sold."""
    df = pd.read_csv(path, parse_dates=["date"])
    required = {"date", "item", "qty_sold"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Sales history is missing columns: {missing}. "
            f"Expected columns: date, item, qty_sold"
        )
    return df


def load_log(path: str | None, qty_col: str) -> pd.DataFrame:
    """Load a receiving or wastage log: date, item, <qty_col>.
    Returns an empty (correctly-shaped) frame if the file doesn't exist
    or hasn't been created yet - logging is optional."""
    empty = pd.DataFrame(columns=["date", "item", qty_col])
    if not path:
        return empty
    try:
        df = pd.read_csv(path, parse_dates=["date"])
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return empty
    if df.empty:
        return empty
    required = {"date", "item", qty_col}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path} is missing columns: {missing}")
    return df


def _match(df: pd.DataFrame, item: str) -> pd.DataFrame:
    if df.empty:
        return df
    return df[df["item"].str.lower() == item.lower()]


# ---------------------------------------------------------------------
# Step 1-3: current stock from receiving + sales + wastage
# ---------------------------------------------------------------------
def compute_current_stock(
    item: str,
    sales: pd.DataFrame,
    receiving: pd.DataFrame,
    wastage: pd.DataFrame,
    as_of_date: pd.Timestamp,
) -> tuple[float, str]:
    """
    current_stock = last_received_qty - (sales_since_receipt + wastage_since_receipt)

    Uses the most recent receiving-log entry for this item as the
    baseline. If nothing has ever been logged as received for this item,
    returns (0.0, ...) so the UI can prompt for a manual entry instead.
    """
    item_recv = _match(receiving, item)
    if item_recv.empty:
        return 0.0, "no receiving log yet - enter stock manually"

    last_recv = item_recv.sort_values("date").iloc[-1]
    recv_date = last_recv["date"]
    recv_qty = float(last_recv["received_qty"])

    item_sales = _match(sales, item)
    sales_since = item_sales[
        (item_sales["date"] > recv_date) & (item_sales["date"] <= as_of_date)
    ]["qty_sold"].sum()

    item_waste = _match(wastage, item)
    waste_since = item_waste[
        (item_waste["date"] > recv_date) & (item_waste["date"] <= as_of_date)
    ]["wastage_qty"].sum()

    current_stock = recv_qty - (sales_since + waste_since)
    note = f"received {recv_qty:g} on {recv_date.date()}, sold {sales_since:g}, wasted {waste_since:g} since"
    return max(round(current_stock, 2), 0.0), note


# ---------------------------------------------------------------------
# Step 4a: previous week's sales for the days this order must cover
# ---------------------------------------------------------------------
def previous_week_sales(
    item: str,
    sales: pd.DataFrame,
    coverage_days: list[str],
    as_of_date: pd.Timestamp,
) -> float:
    """
    Sums last week's qty_sold for this item on the same weekday(s) that
    THIS order needs to cover. coverage_days[0] is the order day itself,
    coverage_days[1:] are the following days until the next order of
    this item's category. Each is looked up 7 days back from as_of_date.
    """
    item_sales = _match(sales, item)
    total = 0.0
    for offset, _weekday in enumerate(coverage_days):
        target_date = as_of_date - pd.Timedelta(days=7) + pd.Timedelta(days=offset)
        day_total = item_sales[item_sales["date"] == target_date]["qty_sold"].sum()
        total += day_total
    return round(float(total), 2)


# ---------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------
def forecast_order(
    order_day: str,
    history_csv: str,
    current_stock: dict[str, float] | None = None,
    receiving_csv: str | None = None,
    wastage_csv: str | None = None,
    sales_log_csv: str | None = None,
    as_of_date=None,
    apply_safety_buffer: bool = False,
    item_master: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Build the order-recommendation table for a given order day.

    current_stock: optional dict of item -> manually-entered stock qty.
        Any item present here (with a non-zero value) OVERRIDES the
        auto-computed current_stock from the receiving/wastage logs -
        useful for shops that haven't started logging yet, or want to
        do a quick manual count.
    sales_log_csv: optional path to sales entered day-to-day inside the
        app (see the "Log Sales" tab). Combined with history_csv so a
        store with no external POS export can still build up history.
    apply_safety_buffer: if True, multiplies the final order qty by
        (1 + safety_buffer_pct/100) from item_master, if provided. Off
        by default, since the manager's formula (prev week sales -
        current stock) doesn't call for one.
    """
    base_sales = load_history(history_csv)
    logged_sales = load_log(sales_log_csv, "qty_sold")
    sales = pd.concat([base_sales, logged_sales], ignore_index=True) if not logged_sales.empty else base_sales

    items = items_for_order_day(order_day)
    if not items:
        return pd.DataFrame()

    # NOTE: we deliberately do NOT bail out here just because `sales` is
    # empty. A brand-new store legitimately starts with zero sales
    # history - it still needs the editable order sheet (with 0's for
    # "Last Week's Sales" until enough days have been logged) rather
    # than a blank screen and no download button.
    if as_of_date is not None:
        as_of_date = pd.Timestamp(as_of_date)
    elif not sales.empty:
        # Use the most recent date in the sales history that actually
        # falls on order_day's weekday, so "previous week" comparisons
        # line up correctly. Falls back to the latest date overall if
        # the history doesn't span a full week yet.
        same_weekday = sales[sales["date"].dt.day_name() == order_day]
        as_of_date = same_weekday["date"].max() if not same_weekday.empty else sales["date"].max()
    else:
        as_of_date = pd.Timestamp.today().normalize()

    receiving = load_log(receiving_csv, "received_qty")
    wastage = load_log(wastage_csv, "wastage_qty")
    current_stock = current_stock or {}

    rows = []
    for item, meta in items.items():
        cov_days = coverage_weekdays(order_day, meta["category"])
        prev_week = previous_week_sales(item, sales, cov_days, as_of_date)

        manual = current_stock.get(item)
        if manual is not None and float(manual) > 0:
            stock, stock_note = round(float(manual), 2), "manual entry"
        else:
            stock, stock_note = compute_current_stock(item, sales, receiving, wastage, as_of_date)

        order_qty = max(prev_week - stock, 0.0)

        if apply_safety_buffer and item_master is not None:
            row = item_master[item_master["item"].str.lower() == item.lower()]
            if not row.empty:
                buffer_pct = float(row["safety_buffer_pct"].values[0])
                order_qty *= (1 + buffer_pct / 100)

        if meta["unit"] == "box":
            order_qty = math.ceil(order_qty)
        else:
            order_qty = round(order_qty, 1)

        rows.append({
            "item": item,
            "category": meta["category"],
            "unit": meta["unit"],
            "coverage_days": len(cov_days),
            "prev_week_sales": prev_week,
            "current_stock": stock,
            "stock_source": stock_note,
            "suggested_order_qty": order_qty,
        })

    df = pd.DataFrame(rows)
    cat_order = {"basic": 0, "other": 1, "fruit": 2}
    df["_sort"] = df["category"].map(cat_order)
    return df.sort_values(["_sort", "item"]).drop(columns="_sort").reset_index(drop=True)
