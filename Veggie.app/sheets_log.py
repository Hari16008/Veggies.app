"""
sheets_log.py
--------------
Google-Sheets-backed persistence for the receiving/wastage/sales logs.

Why: Streamlit Community Cloud's filesystem is EPHEMERAL - it resets on
every reboot, redeploy, and periodic sleep/wake cycle, so the plain CSV
files under data/ silently lose every entry your team logs. This module
keeps entries in a Google Sheet instead, which survives all of that.

It exposes the SAME function shapes streamlit_app.py already calls
(append_entries, read_log) so it's a straight swap, and it falls back
cleanly (raising SheetsNotConfigured) if secrets haven't been set up
yet, so local development without Sheets access doesn't crash.

--------------------------------------------------------------------
ONE-TIME SETUP
--------------------------------------------------------------------
1. Google Cloud Console (console.cloud.google.com) -> create/select a
   project -> "APIs & Services" -> Library -> enable both:
     - Google Sheets API
     - Google Drive API

2. "APIs & Services" -> Credentials -> Create Credentials -> Service
   account. Give it any name (e.g. "veggie-app-sheets"). After it's
   created, open it -> Keys tab -> Add Key -> Create new key -> JSON.
   This downloads a .json file - keep it private, never commit it.

3. Create a new Google Sheet (sheets.new). Name it anything, e.g.
   "Veggie Order Logs". Click Share, and share it with the service
   account's email address (the "client_email" field inside the JSON
   you downloaded, looks like xxx@xxx.iam.gserviceaccount.com) as an
   Editor.

4. Copy the sheet's ID out of its URL:
     https://docs.google.com/spreadsheets/d/  THIS_PART_IS_THE_ID  /edit

5. In Streamlit secrets - locally that's a file at .streamlit/secrets.toml
   (never commit this file - add it to .gitignore); on Streamlit
   Community Cloud it's the "Secrets" box under your app's Settings -
   paste the following, filling in values straight from the JSON key:

        gsheet_key = "paste-the-sheet-id-from-step-4"

        [gcp_service_account]
        type = "service_account"
        project_id = "..."
        private_key_id = "..."
        private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
        client_email = "...@....iam.gserviceaccount.com"
        client_id = "..."
        token_uri = "https://oauth2.googleapis.com/token"

   Every one of those fields is already present in the downloaded JSON
   key under the matching name - copy them across as-is, including the
   \n characters inside private_key exactly as they appear.

6. Add these two lines to requirements.txt:
        gspread
        google-auth

That's it - the three log tabs ("receiving_log", "wastage_log",
"sales_log") are created automatically inside that one spreadsheet the
first time each is written to.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st


class SheetsNotConfigured(RuntimeError):
    """Raised when Streamlit secrets are missing the Sheets setup.
    Callers use this to fall back to local CSV storage instead."""


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def is_configured() -> bool:
    """Cheap check the app can use up front to decide which storage
    backend to use, without triggering an actual API call."""
    return "gcp_service_account" in st.secrets and (
        "gsheet_key" in st.secrets or "gsheet_url" in st.secrets
    )


@st.cache_resource(show_spinner=False)
def _client():
    import gspread
    from google.oauth2.service_account import Credentials

    if "gcp_service_account" not in st.secrets:
        raise SheetsNotConfigured(
            "Missing [gcp_service_account] in Streamlit secrets. "
            "See the setup steps in sheets_log.py's module docstring."
        )
    creds = Credentials.from_service_account_info(dict(st.secrets["gcp_service_account"]), scopes=SCOPES)
    return gspread.authorize(creds)


@st.cache_resource(show_spinner=False)
def _spreadsheet():
    gc = _client()
    key = st.secrets.get("gsheet_key")
    url = st.secrets.get("gsheet_url")
    if key:
        return gc.open_by_key(key)
    if url:
        return gc.open_by_url(url)
    raise SheetsNotConfigured(
        "Missing gsheet_key (or gsheet_url) in Streamlit secrets. "
        "See the setup steps in sheets_log.py's module docstring."
    )


def _worksheet(sheet_name: str, header: list[str]):
    import gspread

    ss = _spreadsheet()
    try:
        return ss.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = ss.add_worksheet(title=sheet_name, rows=2000, cols=max(len(header), 3))
        ws.append_row(header)
        return ws


# ---------------------------------------------------------------------
# Public interface - same call shape as the old inventory_log.py
# ---------------------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=20)
def read_log(sheet_name: str, qty_col: str) -> pd.DataFrame:
    """Read a full log tab as a DataFrame with columns [date, item, qty_col].
    Returns an empty (correctly-shaped) frame if the tab has no rows yet."""
    header = ["date", "item", qty_col]
    empty = pd.DataFrame(columns=header)

    ws = _worksheet(sheet_name, header)  # lets SheetsNotConfigured propagate
    records = ws.get_all_records()
    if not records:
        return empty

    df = pd.DataFrame(records)
    if not {"date", "item", qty_col}.issubset(df.columns):
        return empty

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df[qty_col] = pd.to_numeric(df[qty_col], errors="coerce").fillna(0.0)
    df = df.dropna(subset=["date"])
    return df[["date", "item", qty_col]].reset_index(drop=True)


def append_entries(sheet_name: str, qty_col: str, entry_date, entries: dict) -> int:
    """Append one row per item with qty > 0. Returns how many rows were
    logged. Mirrors the old inventory_log.append_entries signature."""
    header = ["date", "item", qty_col]
    ws = _worksheet(sheet_name, header)

    date_str = entry_date.isoformat() if hasattr(entry_date, "isoformat") else str(entry_date)
    rows = []
    for item, qty in entries.items():
        try:
            qty = float(qty)
        except (TypeError, ValueError):
            continue
        if qty > 0:
            rows.append([date_str, item, qty])

    if rows:
        ws.append_rows(rows, value_input_option="USER_ENTERED")
        read_log.clear()  # bust the cache so the next read reflects this write

    return len(rows)
