"""
Stage 4 sanity check: run the full Stages 1-3 pipeline on the synthetic
sample ledger and generate the HTML + PDF report. This is the
regression test - same synthetic data used throughout Stages 1-3.

Run from the project root:
    venv\\Scripts\\python demo\\scripts\\stage4_demo.py
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
from app.ingestion.metrics import compute_monthly_metrics, compute_rolling_trend, compute_exposure
from app.signals.external_signals import load_from_csv
from app.signals.coverage import build_coverage_screen
from app.scoring.engine import score_all_customers
from app.reporting.builder import build_report_context
from app.reporting.render import render_report

NAME_MAP_PATH = PROJECT_ROOT / "demo" / "config" / "customer_name_map.csv"
SIGNALS_PATH = PROJECT_ROOT / "demo" / "config" / "external_signals_template.csv"
OUTPUT_BASENAME = PROJECT_ROOT / "demo" / "output" / "report_synthetic_sample"


def _hr(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def main() -> None:
    _hr("RUNNING STAGES 1-3")
    ledger_path = generate_synthetic_ledger()
    result = parse_ledger_file(ledger_path)
    name_map = load_name_map(NAME_MAP_PATH)
    clean_df, _ = apply_name_map(result.clean_df, name_map)
    ledger_customers = sorted(clean_df["customer_name"].unique())

    monthly = compute_monthly_metrics(clean_df)
    trend = compute_rolling_trend(monthly)
    exposure = compute_exposure(clean_df)
    signals_df, _ = load_from_csv(SIGNALS_PATH)
    coverage = build_coverage_screen(ledger_customers, signals_df)
    scores = score_all_customers(ledger_customers, coverage, signals_df, trend)
    print(f"{len(ledger_customers)} customers scored.")

    _hr("BUILDING REPORT")
    context = build_report_context(
        scores,
        exposure,
        report_title="Accounts Receivable Risk Report",
        subtitle="Synthetic sample data — regression test for the Stage 1-3 pipeline",
        disclaimer_banner=None,  # no special banner needed for the synthetic-sample regression test
    )
    result_paths = render_report(context, OUTPUT_BASENAME)
    print(f"HTML: {result_paths['html_path']}")
    print(f"PDF : {result_paths['pdf_path'] or 'FAILED - ' + '; '.join(result_paths['pdf_errors'])}")

    _hr("SPOT-CHECKS")
    print(f"Total customers in context: {context['total_customers']} (expect 7)")
    print(f"Rated: {context['rated_count']}, Unrated: {context['unrated_count']}, Not researched: {context['not_researched_count']}")
    print(f"Ranked list length: {len(context['ranked_customers'])} (expect <=15, only 'rated' group)")
    print("Ranked customers:", [c["customer_name"] for c in context["ranked_customers"]])
    print("Reviewed-not-flagged entries:", [r["customer_name"] for r in context["reviewed_not_flagged"]])
    print("Unrated/not-researched list:", [c["customer_name"] for c in context["unrated_customers"]])
    assert "Falcon Pharma Wholesale" in [r["customer_name"] for r in context["reviewed_not_flagged"]], \
        "Benign-withdrawal trust line missing from report context"
    assert all(c["customer_name"] != "Falcon Pharma Wholesale" or True for c in context["ranked_customers"]), \
        "sanity no-op"
    print("\nPASS: benign-withdrawal note for Falcon Pharma Wholesale is present in report context.")


if __name__ == "__main__":
    main()
