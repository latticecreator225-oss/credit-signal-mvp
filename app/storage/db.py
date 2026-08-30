"""
Minimal SQLite persistence for the ledger and computed metrics.

No ORM, no migrations framework: this is a single-client tool run by
one operator for one engagement at a time, not a multi-tenant app - a
thin wrapper around sqlite3 + pandas.to_sql is all that's warranted.
Each pipeline run replaces the tables wholesale (if_exists="replace"),
which is the right behaviour for "re-ingest this client's latest
ledger export", not an oversight.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "credit_signal.db"


def get_connection(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    return sqlite3.connect(db_path)


def save_ledger(clean_df: pd.DataFrame, conn: sqlite3.Connection) -> None:
    clean_df.to_sql("ledger_entries", conn, if_exists="replace", index=False)


def save_monthly_metrics(monthly_df: pd.DataFrame, conn: sqlite3.Connection) -> None:
    out = monthly_df.copy()
    if "invoice_month" in out.columns:
        out["invoice_month"] = out["invoice_month"].astype(str)  # Period isn't sqlite-storable
    out.to_sql("customer_monthly_metrics", conn, if_exists="replace", index=False)


def save_rolling_trend(trend_df: pd.DataFrame, conn: sqlite3.Connection) -> None:
    trend_df.to_sql("customer_rolling_trend", conn, if_exists="replace", index=False)


def save_exposure(exposure_df: pd.DataFrame, conn: sqlite3.Connection) -> None:
    exposure_df.to_sql("customer_exposure", conn, if_exists="replace", index=False)


def save_parse_errors(errors_df: pd.DataFrame, conn: sqlite3.Connection) -> None:
    # kept even when empty, so a report/audit trail always finds the table
    if errors_df.empty:
        errors_df = pd.DataFrame(columns=["source_row_number", "reasons"])
    errors_df.to_sql("ledger_parse_errors", conn, if_exists="replace", index=False)
