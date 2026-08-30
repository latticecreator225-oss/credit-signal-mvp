"""
Stage 1 sanity check: generate the synthetic messy ledger, apply the
manual customer-name override, run the parser and metrics, print
everything for review, persist to SQLite, and drop CSV copies in
output/ for easy viewing outside the terminal.

Run from the project root:
    venv\\Scripts\\python demo\\scripts\\stage1_demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Windows consoles often default to cp1252, which can't encode the Rupee
# sign (or other non-ASCII characters this project's output will contain
# again in later stages, e.g. the Stage 4 report). Force UTF-8 on stdout
# rather than avoiding the character.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from demo.data_generators.sample_generator import generate_synthetic_ledger
from app.ingestion.parser import parse_ledger_file
from app.ingestion.name_map import load_name_map, apply_name_map
from app.ingestion.metrics import compute_monthly_metrics, compute_rolling_trend, compute_exposure
from app.storage.db import (
    get_connection, save_ledger, save_monthly_metrics,
    save_rolling_trend, save_exposure, save_parse_errors,
)

OUTPUT_DIR = PROJECT_ROOT / "demo" / "output"
NAME_MAP_PATH = PROJECT_ROOT / "demo" / "config" / "customer_name_map.csv"

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 20)
pd.set_option("display.max_rows", 60)


def _hr(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def main() -> None:
    _hr("1. GENERATING SYNTHETIC SAMPLE LEDGER")
    path = generate_synthetic_ledger()
    print(f"Wrote {path}")

    _hr("2. PARSING")
    result = parse_ledger_file(path)
    print(result.summary())

    _hr("3. QUARANTINED ROWS (errors_df) — nothing silently dropped")
    if result.errors_df.empty:
        print("(none)")
    else:
        print(result.errors_df[["source_row_number", "reasons"]].to_string(index=False))

    _hr("4. CUSTOMER NAME OVERRIDE (config/customer_name_map.csv)")
    name_map = load_name_map(NAME_MAP_PATH)
    print(f"Loaded {len(name_map)} override(s): {name_map}")
    raw_names_before = sorted(result.clean_df["customer_name"].unique())
    print(f"\nDistinct customer names BEFORE mapping ({len(raw_names_before)}):")
    for n in raw_names_before:
        print(f"  - {n}")
    clean_df, name_map_report = apply_name_map(result.clean_df, name_map)
    raw_names_after = sorted(clean_df["customer_name"].unique())
    print(f"\nDistinct customer names AFTER mapping ({len(raw_names_after)}):")
    for n in raw_names_after:
        print(f"  - {n}")
    print(f"\nMapped (renamed)   : {name_map_report['mapped']}")
    print(f"Unmapped (as-is)   : {name_map_report['unmapped']}")
    print(f"Unused overrides   : {name_map_report['unused_overrides']}")

    _hr("5. CLEAN LEDGER (canonical schema, post name-mapping) — first 10 rows")
    print(clean_df.head(10).to_string(index=False))
    print(f"... {len(clean_df)} rows total")

    _hr("6. PER-CUSTOMER, PER-MONTH METRICS")
    monthly = compute_monthly_metrics(clean_df)
    print(monthly.to_string(index=False))

    _hr("7. ROLLING TREND (recent 3 months vs. prior 3 months)")
    trend = compute_rolling_trend(monthly)
    print(trend.to_string(index=False))
    print(
        "\nRead this as: Orchid Pharma Distributors should show a large positive "
        "days_to_pay_pct_change (drift toward slower payment); Neuland Traders "
        "should show something close to 0%. Kwality Distributors should reflect "
        "the merged Pvt. Ltd. invoices as part of its own history, not a "
        "separate customer."
    )

    _hr("8. SPARSE-DATA CHECK: Vertex Pharma Retail & Bright Health Distributors")
    sparse = trend[trend["customer_name"].isin(
        ["Vertex Pharma Retail", "Bright Health Distributors"]
    )]
    print(sparse.to_string(index=False))
    print(
        "\nVertex Pharma Retail: 2 invoices, both in July 2024 -> 1 month of "
        "history. 'recent' window absorbs that 1 month; 'prior' window has 0 "
        "months, so prior_avg_days_to_pay and days_to_pay_pct_change are both "
        "correctly None/NaN - not fabricated, not a crash.\n"
        "\n"
        "Bright Health Distributors: invoices in Jan 2024, then a 5-month gap, "
        "then more in Jul 2024 -> 2 months of history, but 'recent 3 months' "
        "silently means 'the last 3 calendar months that had ANY invoice', not "
        "the last 3 wall-clock months - so it ends up averaging Jan and Jul "
        "together as if they were adjacent. That's a real behavior to know "
        "about, not a bug I'm hiding: a sparse customer's 'recent' trend can "
        "span a much wider time window than the name implies."
    )

    _hr("9. OUTSTANDING EXPOSURE (as of the latest date in the ledger) — every customer, incl. ₹0")
    exposure = compute_exposure(clean_df)
    print(exposure.to_string(index=False))

    _hr("10. PERSISTING TO SQLITE")
    conn = get_connection()
    save_ledger(clean_df, conn)
    save_monthly_metrics(monthly, conn)
    save_rolling_trend(trend, conn)
    save_exposure(exposure, conn)
    save_parse_errors(result.errors_df, conn)
    conn.close()
    print("Saved tables: ledger_entries, customer_monthly_metrics, "
          "customer_rolling_trend, customer_exposure, ledger_parse_errors")
    print(f"DB file: {PROJECT_ROOT / 'credit_signal.db'}")

    _hr("11. WRITING CSV COPIES TO output/ FOR EASY VIEWING")
    OUTPUT_DIR.mkdir(exist_ok=True)
    clean_df.to_csv(OUTPUT_DIR / "clean_ledger.csv", index=False)
    result.errors_df.to_csv(OUTPUT_DIR / "parse_errors.csv", index=False)
    monthly_out = monthly.copy()
    monthly_out["invoice_month"] = monthly_out["invoice_month"].astype(str)
    monthly_out.to_csv(OUTPUT_DIR / "monthly_metrics.csv", index=False)
    trend.to_csv(OUTPUT_DIR / "rolling_trend.csv", index=False)
    exposure.to_csv(OUTPUT_DIR / "exposure.csv", index=False)
    for f in ["clean_ledger.csv", "parse_errors.csv", "monthly_metrics.csv",
              "rolling_trend.csv", "exposure.csv"]:
        print(f"  demo/output/{f}")


if __name__ == "__main__":
    main()
