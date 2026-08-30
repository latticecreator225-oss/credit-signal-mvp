"""
Stage 2 sanity check: run the Stage 1 pipeline, load the manually
researched external-signals template, build the coverage screen, and
show all of it for review.

Run from the project root (after stage1_demo.py has been reviewed):
    venv\\Scripts\\python demo\\scripts\\stage2_demo.py
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
from app.signals.external_signals import load_from_csv
from app.signals.coverage import build_coverage_screen, RATED, UNRATED, NOT_YET_RESEARCHED
from app.storage.db import get_connection

OUTPUT_DIR = PROJECT_ROOT / "demo" / "output"
NAME_MAP_PATH = PROJECT_ROOT / "demo" / "config" / "customer_name_map.csv"
SIGNALS_PATH = PROJECT_ROOT / "demo" / "config" / "external_signals_template.csv"

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 20)


def _hr(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def main() -> None:
    _hr("1. RE-RUNNING STAGE 1 (parser + name map) TO GET THE CUSTOMER LIST")
    ledger_path = generate_synthetic_ledger()
    result = parse_ledger_file(ledger_path)
    name_map = load_name_map(NAME_MAP_PATH)
    clean_df, _ = apply_name_map(result.clean_df, name_map)
    ledger_customers = sorted(clean_df["customer_name"].unique())
    print(f"{len(ledger_customers)} customers in the ledger: {ledger_customers}")

    _hr("2. LOADING EXTERNAL SIGNALS (config/external_signals_template.csv)")
    signals_df, warnings = load_from_csv(SIGNALS_PATH)
    print(f"Loaded {len(signals_df)} signal row(s).")
    print(f"\nWarnings ({len(warnings)}) - rows are KEPT with the bad field left unknown, not dropped:")
    for w in warnings:
        print(f"  - {w}")

    _hr("3. EXTERNAL SIGNALS TABLE (as loaded)")
    print(signals_df.to_string(index=False))

    _hr("4. COVERAGE SCREEN — every ledger customer, three states")
    coverage = build_coverage_screen(ledger_customers, signals_df)
    print(coverage.to_string(index=False))

    counts = coverage["coverage_status"].value_counts()
    print(f"\n  {RATED:<20}: {counts.get(RATED, 0)}")
    print(f"  {UNRATED:<20}: {counts.get(UNRATED, 0)}")
    print(f"  {NOT_YET_RESEARCHED:<20}: {counts.get(NOT_YET_RESEARCHED, 0)}")
    print(
        "\nCheck: 'Deliberately Malformed Test Row' is in the signals CSV but is not a "
        "ledger customer, so it correctly does not appear in the coverage screen at all "
        "- the coverage screen is driven by who's in the LEDGER, not who has a signals row.\n"
        "Check: Vertex Pharma Retail has no row in the signals CSV at all -> "
        f"'{NOT_YET_RESEARCHED}', not silently absent and not lumped in with '{UNRATED}'.\n"
        f"Check: Sunrise Pharma Corp and Bright Health Distributors were actively researched "
        f"and confirmed to have no public rating -> '{UNRATED}', a different fact from "
        f"'{NOT_YET_RESEARCHED}' even though both currently show no rating-based score."
    )

    _hr("5. PERSISTING TO SQLITE")
    conn = get_connection()
    signals_df.to_sql("external_signals", conn, if_exists="replace", index=False)
    coverage.to_sql("coverage_screen", conn, if_exists="replace", index=False)
    conn.close()
    print("Saved tables: external_signals, coverage_screen")

    _hr("6. WRITING CSV COPIES TO output/")
    OUTPUT_DIR.mkdir(exist_ok=True)
    signals_df.to_csv(OUTPUT_DIR / "external_signals.csv", index=False)
    coverage.to_csv(OUTPUT_DIR / "coverage_screen.csv", index=False)
    print("  output/external_signals.csv")
    print("  output/coverage_screen.csv")


if __name__ == "__main__":
    main()
