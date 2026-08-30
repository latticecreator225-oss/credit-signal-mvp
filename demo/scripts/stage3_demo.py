"""
Stage 3 sanity check: run Stages 1-2, score every customer, and show the
Orchid Pharma Distributors vs. Neuland Traders comparison specifically
(the deteriorating-payer vs. the flat/healthy control from the Stage 1
synthetic ledger) before touching Stage 4.

Run from the project root:
    venv\\Scripts\\python demo\\scripts\\stage3_demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from demo.data_generators.sample_generator import generate_synthetic_ledger
from app.ingestion.parser import parse_ledger_file
from app.ingestion.name_map import load_name_map, apply_name_map
from app.ingestion.metrics import compute_monthly_metrics, compute_rolling_trend
from app.signals.external_signals import load_from_csv
from app.signals.coverage import build_coverage_screen
from app.scoring.engine import score_all_customers
from app.storage.db import get_connection

OUTPUT_DIR = PROJECT_ROOT / "demo" / "output"
NAME_MAP_PATH = PROJECT_ROOT / "demo" / "config" / "customer_name_map.csv"
SIGNALS_PATH = PROJECT_ROOT / "demo" / "config" / "external_signals_template.csv"

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)
pd.set_option("display.max_colwidth", 100)


def _hr(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def main() -> None:
    _hr("1. RUNNING STAGES 1-2 TO BUILD THE SCORING INPUTS")
    ledger_path = generate_synthetic_ledger()
    result = parse_ledger_file(ledger_path)
    name_map = load_name_map(NAME_MAP_PATH)
    clean_df, _ = apply_name_map(result.clean_df, name_map)
    ledger_customers = sorted(clean_df["customer_name"].unique())

    monthly = compute_monthly_metrics(clean_df)
    trend = compute_rolling_trend(monthly)
    signals_df, signal_warnings = load_from_csv(SIGNALS_PATH)
    coverage = build_coverage_screen(ledger_customers, signals_df)
    print(f"{len(ledger_customers)} customers, {len(signal_warnings)} signal-loading warning(s) (expected - see Stage 2).")

    _hr("2. GAP-EXCLUSION CHECK (new this stage)")
    gap_cols = ["customer_name", "months_of_history", "trend_data_quality", "days_to_pay_pct_change"]
    print(trend[gap_cols].to_string(index=False))
    print(
        "\nBright Health Distributors should show trend_data_quality='gap_exceeds_threshold' "
        "(Jan then Jul, a 6-month gap > the 3-month config threshold) with days_to_pay_pct_change "
        "left blank - NOT averaged across the gap.\n"
        "Vertex Pharma Retail should show trend_data_quality='too_few_invoices' (1 month of "
        "history, no gap involved, just not enough history yet) - a DIFFERENT reason, as required."
    )

    _hr("3. SCORING ALL 6 CUSTOMERS")
    scores = score_all_customers(ledger_customers, coverage, signals_df, trend)
    print(scores[["customer_name", "score", "coverage_status", "fired_signals"]].to_string(index=False))

    _hr("4. THE REQUESTED SANITY CHECK: Orchid Pharma Distributors vs. Neuland Traders")
    pair = scores[scores["customer_name"].isin(["Orchid Pharma Distributors", "Neuland Traders"])]
    for _, row in pair.iterrows():
        print(f"\n{row['customer_name']}  ->  score = {row['score']}")
        print(f"  fired signals: {row['fired_signals']}")
        print(f"  evidence: {row['evidence']}")
    orchid_score = int(scores.loc[scores["customer_name"] == "Orchid Pharma Distributors", "score"].iloc[0])
    neuland_score = int(scores.loc[scores["customer_name"] == "Neuland Traders", "score"].iloc[0])
    print(f"\nOrchid Pharma Distributors ({orchid_score}) vs. Neuland Traders ({neuland_score}): "
          f"{'PASS - Orchid scores higher' if orchid_score > neuland_score else 'FAIL - investigate before Stage 4'}")
    assert orchid_score > neuland_score, "Sanity check failed: Orchid did not outscore Neuland"

    _hr("5. FULL EVIDENCE SENTENCES — ALL 6 CUSTOMERS (this is the actual deliverable, not the score)")
    for _, row in scores.iterrows():
        print(f"\n{row['customer_name']} (score {row['score']}, {row['coverage_status']}):")
        print(f"  {row['evidence']}")

    _hr("6. PERSISTING TO SQLITE")
    conn = get_connection()
    trend.to_sql("customer_rolling_trend", conn, if_exists="replace", index=False)
    scores.to_sql("customer_scores", conn, if_exists="replace", index=False)
    conn.close()
    print("Saved tables: customer_rolling_trend (updated), customer_scores")

    _hr("7. WRITING CSV COPIES TO output/")
    OUTPUT_DIR.mkdir(exist_ok=True)
    trend.to_csv(OUTPUT_DIR / "rolling_trend.csv", index=False)
    scores.to_csv(OUTPUT_DIR / "customer_scores.csv", index=False)
    print("  output/rolling_trend.csv (updated)")
    print("  output/customer_scores.csv")


if __name__ == "__main__":
    main()
