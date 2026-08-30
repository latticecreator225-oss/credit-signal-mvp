"""
Builds the Orchid Pharma Limited (2017) illustrative case-study ledger.

Reuses the exact days-to-pay PATTERN already verified in the Stage 1
synthetic sample (23/23/23/23/26/26 days drifting to 45/51/51/54/55/56),
re-dated to Oct 2016-Mar 2017 so it sits chronologically before the real
external signal this case study is built around.

What is REAL and sourced, and must not be altered without re-verifying
the source:
  - Company: Orchid Pharma Limited, Chennai-based cephalosporin API
    manufacturer.
  - Signal: CARE Ratings downgraded long-term facilities to CARE D from
    CARE B- (short-term: CARE D from CARE A4), 18 April 2017.
  - Outcome: NCLT Chennai admitted Orchid Pharma into CIRP, 17 August
    2017 (Lakshmi Vilas Bank, operational creditor) - a ~4-month gap
    between signal and filing.
  - Control: Neuland Laboratories, a size/sector-matched API
    manufacturer (FY17 revenue ~Rs 579 Cr vs. Orchid's ~Rs 683 Cr),
    showed no adverse rating action over the same window and remained
    a going concern.

What is ILLUSTRATIVE, not real: every invoice-level number below (dates,
amounts, day-counts). No public AR ledger exists for either company;
this is a constructed demonstration of what the tool's OUTPUT would
look like layered onto real external facts, not a reconstruction of
either company's actual books. The report this feeds carries a
permanent banner saying exactly that.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "demo" / "sample_data" / "case_study_ledger.csv"

COLUMNS = ["customer_name", "invoice_id", "invoice_date", "due_date", "payment_date", "invoice_amount", "credit_note_flag", "dispute_flag"]

# (customer, invoice_id, invoice_date, due_date, payment_date_or_None, amount)
_ROWS = [
    # --- Orchid Pharma Limited: same drift pattern verified in Stage 1
    # (23/23/23/23/26/26 -> 45/51/51/54/55/56 days), re-dated to precede
    # the real 18-Apr-2017 signal.
    ("Orchid Pharma Limited", "OPL-4401", date(2016, 10, 5), date(2016, 11, 4), date(2016, 10, 28), 340000),
    ("Orchid Pharma Limited", "OPL-4415", date(2016, 10, 18), date(2016, 11, 17), date(2016, 11, 10), 210000),
    ("Orchid Pharma Limited", "OPL-4432", date(2016, 11, 8), date(2016, 12, 8), date(2016, 12, 1), 275000),
    ("Orchid Pharma Limited", "OPL-4448", date(2016, 11, 22), date(2016, 12, 22), date(2016, 12, 15), 190000),
    ("Orchid Pharma Limited", "OPL-4461", date(2016, 12, 10), date(2017, 1, 9), date(2017, 1, 5), 320000),
    ("Orchid Pharma Limited", "OPL-4477", date(2016, 12, 25), date(2017, 1, 24), date(2017, 1, 20), 260000),
    ("Orchid Pharma Limited", "OPL-4490", date(2017, 1, 5), date(2017, 2, 4), date(2017, 2, 19), 300000),
    ("Orchid Pharma Limited", "OPL-4504", date(2017, 1, 20), date(2017, 2, 19), date(2017, 3, 12), 245000),
    ("Orchid Pharma Limited", "OPL-4519", date(2017, 2, 5), date(2017, 3, 7), date(2017, 3, 28), 355000),
    ("Orchid Pharma Limited", "OPL-4533", date(2017, 2, 22), date(2017, 3, 24), date(2017, 4, 17), 280000),
    ("Orchid Pharma Limited", "OPL-4550", date(2017, 3, 8), date(2017, 4, 7), date(2017, 5, 2), 310000),
    ("Orchid Pharma Limited", "OPL-4566", date(2017, 3, 25), date(2017, 4, 24), date(2017, 5, 20), 265000),

    # --- Neuland Laboratories: same flat/healthy pattern as the
    # synthetic control, same window.
    ("Neuland Laboratories", "NL-2201", date(2016, 10, 8), date(2016, 11, 7), date(2016, 11, 5), 180000),
    ("Neuland Laboratories", "NL-2212", date(2016, 10, 24), date(2016, 11, 23), date(2016, 11, 22), 150000),
    ("Neuland Laboratories", "NL-2228", date(2016, 11, 10), date(2016, 12, 10), date(2016, 12, 10), 165000),
    ("Neuland Laboratories", "NL-2240", date(2016, 11, 27), date(2016, 12, 27), date(2016, 12, 26), 175000),
    ("Neuland Laboratories", "NL-2256", date(2016, 12, 12), date(2017, 1, 11), date(2017, 1, 10), 190000),
    ("Neuland Laboratories", "NL-2270", date(2016, 12, 28), date(2017, 1, 27), date(2017, 1, 28), 160000),
    ("Neuland Laboratories", "NL-2285", date(2017, 1, 9), date(2017, 2, 8), date(2017, 2, 7), 200000),
    ("Neuland Laboratories", "NL-2298", date(2017, 1, 24), date(2017, 2, 23), date(2017, 2, 24), 155000),
    ("Neuland Laboratories", "NL-2312", date(2017, 2, 11), date(2017, 3, 13), date(2017, 3, 14), 210000),
    ("Neuland Laboratories", "NL-2325", date(2017, 2, 27), date(2017, 3, 29), date(2017, 3, 25), 170000),
    ("Neuland Laboratories", "NL-2340", date(2017, 3, 9), date(2017, 4, 8), date(2017, 4, 8), 195000),
    ("Neuland Laboratories", "NL-2355", date(2017, 3, 26), date(2017, 4, 25), date(2017, 4, 26), 180000),

    # --- Ashoka Pharma Distributors: the deliberately imperfect element.
    # 2 invoices, one month, one still unpaid - "too_few_invoices" trend
    # status AND "not_yet_researched" coverage (no external-signals row
    # for it below), the same way Vertex Pharma Retail behaves in the
    # synthetic set. A real engagement will have customers like this;
    # a case study with none would be misleadingly cleaner than reality.
    ("Ashoka Pharma Distributors", "APD-01", date(2017, 3, 4), date(2017, 4, 3), date(2017, 3, 30), 98000),
    ("Ashoka Pharma Distributors", "APD-02", date(2017, 3, 19), date(2017, 4, 18), None, 115000),
]


def generate_case_study_ledger(path: Path = OUTPUT_PATH) -> Path:
    rows = []
    for customer, inv_id, inv_date, due_date, pay_date, amount in _ROWS:
        rows.append({
            "customer_name": customer,
            "invoice_id": inv_id,
            "invoice_date": inv_date.isoformat(),
            "due_date": due_date.isoformat(),
            "payment_date": pay_date.isoformat() if pay_date else "",
            "invoice_amount": amount,
            "credit_note_flag": "N",
            "dispute_flag": "No",
        })
    df = pd.DataFrame(rows, columns=COLUMNS)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path


if __name__ == "__main__":
    out = generate_case_study_ledger()
    print(f"Wrote {out}")
