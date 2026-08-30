#!/usr/bin/env python
"""
Run the AR-risk pipeline against a real client's ledger and produce a
report. This is the actual delivery mechanism for a paid engagement -
runs entirely on your machine, nothing is uploaded anywhere. That's
deliberate: a real ledger is commercially sensitive client data, which
is exactly why this stays a local script rather than the Streamlit demo
app or any hosted service.

Before running this for a new client:
  1. Copy templates/external_signals_template.csv somewhere for this
     engagement, delete the EXAMPLE row, and fill it in with researched
     signals (see templates/ for the field reference).
  2. If the ledger has customer-name variants ("Acme Ltd" vs
     "Acme Limited"), copy templates/customer_name_map_template.csv too
     and fill in the mapping. Optional - omit --name-map if not needed.

Usage:
    python run_pipeline.py \
        --ledger path/to/client_ledger.csv \
        --signals path/to/client_signals.csv \
        [--name-map path/to/client_name_map.csv] \
        [--out output/client_name/report] \
        [--title "Acme Corp — Accounts Receivable Risk Report"]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.ingestion.parser import parse_ledger_file
from app.ingestion.name_map import load_name_map, apply_name_map
from app.ingestion.metrics import compute_monthly_metrics, compute_rolling_trend, compute_exposure
from app.signals.external_signals import load_from_csv
from app.signals.coverage import build_coverage_screen
from app.scoring.engine import score_all_customers
from app.reporting.builder import build_report_context
from app.reporting.render import render_report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the AR-risk pipeline against a client ledger and produce a report.",
    )
    parser.add_argument("--ledger", required=True, type=Path, help="Client AR ledger (CSV/Excel)")
    parser.add_argument("--signals", required=True, type=Path, help="Filled-in external-signals CSV for this engagement")
    parser.add_argument("--name-map", type=Path, default=None, help="Optional customer name-map CSV")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "output" / "report", help="Output path prefix (no extension) - writes <prefix>.html and <prefix>.pdf")
    parser.add_argument("--title", default="Accounts Receivable Risk Report", help="Report title")
    parser.add_argument("--subtitle", default="", help="Report subtitle (e.g. client name and date)")
    args = parser.parse_args()

    print(f"Parsing {args.ledger} ...")
    result = parse_ledger_file(args.ledger)
    print(result.summary())
    if result.error_row_count:
        print(f"\n{result.error_row_count} row(s) quarantined - review before trusting this report:")
        print(result.errors_df[["source_row_number", "reasons"]].to_string(index=False))

    clean_df = result.clean_df
    if args.name_map:
        name_map = load_name_map(args.name_map)
        clean_df, name_map_report = apply_name_map(clean_df, name_map)
        print(f"\nName map: {len(name_map_report['mapped'])} customer(s) renamed.")
        if name_map_report["unmapped"]:
            print(f"  Not in the map (kept as-is): {name_map_report['unmapped']}")
        if name_map_report["unused_overrides"]:
            print(f"  WARNING - override entries that matched nothing in this ledger (check for typos): {name_map_report['unused_overrides']}")

    if clean_df.empty:
        print("\nNo usable rows in this ledger. Stopping - nothing to score.")
        sys.exit(1)

    ledger_customers = sorted(clean_df["customer_name"].unique())
    monthly = compute_monthly_metrics(clean_df)
    trend = compute_rolling_trend(monthly)
    exposure = compute_exposure(clean_df)

    print(f"\nLoading external signals from {args.signals} ...")
    signals_df, warnings = load_from_csv(args.signals)
    if warnings:
        print(f"{len(warnings)} row(s) in the signals file had issues - fix and re-run before sending this report:")
        for w in warnings:
            print(f"  - {w}")

    coverage = build_coverage_screen(ledger_customers, signals_df)
    scores = score_all_customers(ledger_customers, coverage, signals_df, trend)
    context = build_report_context(scores, exposure, report_title=args.title, subtitle=args.subtitle)

    result_paths = render_report(context, args.out)
    print(f"\nWrote {result_paths['html_path']}")
    if result_paths["pdf_path"]:
        print(f"Wrote {result_paths['pdf_path']}")
    else:
        print(f"PDF generation failed ({result_paths['pdf_errors']}) - HTML report above is still valid, open it in a browser.")

    print(
        f"\n{context['rated_count']} rated, {context['unrated_count']} unrated, "
        f"{context['not_researched_count']} not-yet-researched, out of {context['total_customers']} total.\n"
        f"Review the report yourself before sending it to the client - the score is secondary, "
        f"the evidence sentences are what you're being paid to get right."
    )


if __name__ == "__main__":
    main()
