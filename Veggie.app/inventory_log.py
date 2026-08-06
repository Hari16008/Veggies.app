"""
inventory_log.py
-----------------
Tiny append-only CSV logger for the two events staff record during the
order cycle:
  - receiving: when veggies arrive, logged by weight (or box for
    coriander/mint)
  - wastage:   spoilage/discards pulled off the shelf, logged the same way

Both logs are plain CSVs so they're easy to inspect, back up, or edit
by hand if a correction is needed. Kept deliberately simple (no DB)
since this is a single-store deployment on Streamlit Cloud.
"""

from __future__ import annotations

import os
import pandas as pd


def _ensure_file(path: str, qty_col: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        pd.DataFrame(columns=["date", "item", qty_col]).to_csv(path, index=False)


def append_entry(path: str, qty_col: str, date, item: str, qty: float) -> None:
    """Append one receiving/wastage row and persist it."""
    _ensure_file(path, qty_col)
    new_row = pd.DataFrame([{"date": pd.Timestamp(date).date().isoformat(), "item": item, qty_col: qty}])
    new_row.to_csv(path, mode="a", header=False, index=False)


def append_entries(path: str, qty_col: str, date, entries: dict[str, float]) -> int:
    """
    Append multiple items at once (e.g. everything entered in a data
    editor table for a single receiving/wastage session). Skips zero
    entries. Returns how many rows were written.
    """
    _ensure_file(path, qty_col)
    rows = [
        {"date": pd.Timestamp(date).date().isoformat(), "item": item, qty_col: qty}
        for item, qty in entries.items()
        if qty and float(qty) > 0
    ]
    if not rows:
        return 0
    pd.DataFrame(rows).to_csv(path, mode="a", header=False, index=False)
    return len(rows)


def read_log(path: str, qty_col: str) -> pd.DataFrame:
    _ensure_file(path, qty_col)
    df = pd.read_csv(path, parse_dates=["date"])
    return df.sort_values("date", ascending=False)
