"""
Generates the Orchid Pharma Limited (2017) illustrative case-study
report: real, sourced external signal (CARE downgrade -> NCLT CIRP,
4-month lead time) and a real matched control (Neuland Laboratories),
with illustrative AR-ledger figures layered on top since no public
ledger exists for either company. Carries a permanent disclaimer
banner; see demo/data_generators/case_study_generator.py for exactly what
is real vs. illustrative in this dataset.

Run from the project root:
    venv\\Scripts\\python demo\\scripts\\generate_case_study_report.py
"""
from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from demo.data_generators.case_study_generator import generate_case_study_ledger
from app.ingestion.parser import parse_ledger_file
from app.ingestion.metrics import compute_monthly_metrics, compute_rolling_trend, compute_exposure
from app.signals.external_signals import load_from_csv
from app.signals.coverage import build_coverage_screen
from app.scoring.engine import score_all_customers
from app.reporting.builder import build_report_context
from app.reporting.render import render_report

SIGNALS_PATH = PROJECT_ROOT / "demo" / "config" / "case_study_external_signals.csv"
OUTPUT_BASENAME = PROJECT_ROOT / "demo" / "output" / "report_orchid_case_study"

DISCLAIMER = (
    "Illustrative output, built from a public case study (Orchid Pharma, 2017) "
    "— not a live client engagement."
)


def _hr(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def main() -> None:
    _hr("BUILDING CASE STUDY DATA")
    ledger_path = generate_case_study_ledger()
    result = parse_ledger_file(ledger_path)
    if result.error_row_count:
        raise RuntimeError(f"Case study ledger produced {result.error_row_count} unexpected parse error(s) - fix the source data, don't ship a report built on rows that failed to parse.")
    ledger_customers = sorted(result.clean_df["customer_name"].unique())
    print(f"Customers: {ledger_customers}")

    monthly = compute_monthly_metrics(result.clean_df)
    trend = compute_rolling_trend(monthly)
    exposure = compute_exposure(result.clean_df)
    signals_df, warnings = load_from_csv(SIGNALS_PATH)
    if warnings:
        raise RuntimeError(f"Case study external-signals file produced unexpected warnings: {warnings}")
    coverage = build_coverage_screen(ledger_customers, signals_df)
    scores = score_all_customers(ledger_customers, coverage, signals_df, trend)

    _hr("SCORES")
    print(scores[["customer_name", "score", "coverage_status", "fired_signals"]].to_string(index=False))

    orchid_score = int(scores.loc[scores["customer_name"] == "Orchid Pharma Limited", "score"].iloc[0])
    neuland_score = int(scores.loc[scores["customer_name"] == "Neuland Laboratories", "score"].iloc[0])
    assert orchid_score > neuland_score, "Orchid Pharma Limited must outscore Neuland Laboratories - check the data"
    assert "Ashoka Pharma Distributors" in coverage.loc[coverage["coverage_status"] == "not_yet_researched", "customer_name"].values, \
        "The deliberately-imperfect customer must land in not_yet_researched - check the setup"
    print(f"\nPASS: Orchid Pharma Limited ({orchid_score}) outscores Neuland Laboratories ({neuland_score}); "
          f"Ashoka Pharma Distributors correctly lands in not_yet_researched.")

    _hr("BUILDING REPORT")
    context = build_report_context(
        scores,
        exposure,
        report_title="Accounts Receivable Risk Report — Illustrative Case Study",
        subtitle="Orchid Pharma Limited (2017) vs. Neuland Laboratories — built from a real, sourced historical signal",
        disclaimer_banner=DISCLAIMER,
    )
    result_paths = render_report(context, OUTPUT_BASENAME)
    print(f"HTML: {result_paths['html_path']}")
    print(f"PDF : {result_paths['pdf_path'] or 'FAILED - ' + '; '.join(result_paths['pdf_errors'])}")

    _hr("REQUIRED-ELEMENTS CHECK")
    html_text = Path(result_paths["html_path"]).read_text(encoding="utf-8")
    checks = {
        "Disclaimer banner text present": DISCLAIMER in html_text,
        "Real CARE downgrade date (18 April 2017) in evidence": "April 2017" in html_text,
        "Methodology note has the real backtest numbers (1/9, 0/5)": "1 confirmed" in html_text and "0 confirmed false positives out of 5" in html_text,
        "Imperfect customer (Ashoka) appears in unrated/not-researched section": "Ashoka Pharma Distributors" in html_text,
    }
    for label, ok in checks.items():
        print(f"  [{'OK' if ok else 'FAIL'}] {label}")
    assert all(checks.values()), "One or more required report elements are missing - see failures above"


if __name__ == "__main__":
    main()
