"""
Builds a small, deliberately messy synthetic AR ledger for sanity-checking
the Stage 1 pipeline before any real client data touches it.

Deliberately includes: inconsistent column headers (mix of exact aliases
and near-misses that require fuzzy matching), four different date string
formats, three different amount formatting styles (plain / comma-grouped
/ currency-symbol), and five rows that are individually broken in a
different way each, to prove the parser quarantines-and-reports rather
than silently drops them.

Four customers, chosen to produce a specific, checkable pattern:
  - Orchid Pharma Distributors : clear payment-behaviour drift (~24 days
    in Q1 -> ~55 days by Q2/Q3) - this is the one that should score high
    on the internal DSO-drift signal once Stage 3 exists.
  - Neuland Traders            : flat, healthy ~29-31 days throughout -
    the control, should show no drift.
  - Sunrise Pharma Corp        : stable ~35-37 days, with two disputed
    invoices and one credit note, to exercise those code paths.
  - Kwality Distributors       : stable payer with two invoices still
    open (unpaid) at the end of the data, to exercise the exposure calc.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "demo" / "sample_data" / "sample_ledger.csv"

COLUMNS = ["Client Name", "Inv No", "Inv Dt", "Due Dt", "Paid On", "Amt (INR)", "CN?", "Disputed?"]

DATE_FORMATS = ["%d/%m/%Y", "%Y-%m-%d", "%d-%b-%y", "%d %B %Y"]


def _fmt_date(d: date | None, style: int) -> str:
    if d is None:
        return ""
    return d.strftime(DATE_FORMATS[style % len(DATE_FORMATS)])


def _fmt_amount(value: float, style: int) -> str:
    style = style % 3
    if style == 0:
        return f"Rs.{value:,.2f}"
    if style == 1:
        return f"{value:,.0f}"
    return str(int(value))


# (customer, invoice_id, invoice_date, due_date, payment_date_or_None, amount, is_cn, is_disputed)
_GOOD_ROWS = [
    # --- Orchid Pharma Distributors: fast (~23-26d) then drifting to ~55d
    ("Orchid Pharma Distributors", "ORC-1001", date(2024, 1, 5), date(2024, 2, 4), date(2024, 1, 28), 340000, False, False),
    ("Orchid Pharma Distributors", "ORC-1015", date(2024, 1, 18), date(2024, 2, 17), date(2024, 2, 10), 210000, False, False),
    ("Orchid Pharma Distributors", "ORC-1032", date(2024, 2, 8), date(2024, 3, 9), date(2024, 3, 2), 275000, False, False),
    ("Orchid Pharma Distributors", "ORC-1048", date(2024, 2, 22), date(2024, 3, 23), date(2024, 3, 16), 190000, False, False),
    ("Orchid Pharma Distributors", "ORC-1061", date(2024, 3, 10), date(2024, 4, 9), date(2024, 4, 5), 320000, False, False),
    ("Orchid Pharma Distributors", "ORC-1077", date(2024, 3, 25), date(2024, 4, 24), date(2024, 4, 20), 260000, False, False),
    ("Orchid Pharma Distributors", "ORC-1090", date(2024, 4, 5), date(2024, 5, 5), date(2024, 5, 20), 300000, False, False),
    ("Orchid Pharma Distributors", "ORC-1104", date(2024, 4, 20), date(2024, 5, 20), date(2024, 6, 10), 245000, False, False),
    ("Orchid Pharma Distributors", "ORC-1119", date(2024, 5, 5), date(2024, 6, 4), date(2024, 6, 25), 355000, False, False),
    ("Orchid Pharma Distributors", "ORC-1133", date(2024, 5, 22), date(2024, 6, 21), date(2024, 7, 15), 280000, False, False),
    ("Orchid Pharma Distributors", "ORC-1150", date(2024, 6, 8), date(2024, 7, 8), date(2024, 8, 2), 310000, False, False),
    ("Orchid Pharma Distributors", "ORC-1166", date(2024, 6, 25), date(2024, 7, 25), date(2024, 8, 20), 265000, False, False),

    # --- Neuland Traders: flat, healthy ~29-31 days
    ("Neuland Traders", "NEU-501", date(2024, 1, 8), date(2024, 2, 7), date(2024, 2, 5), 180000, False, False),
    ("Neuland Traders", "NEU-512", date(2024, 1, 24), date(2024, 2, 23), date(2024, 2, 22), 150000, False, False),
    ("Neuland Traders", "NEU-528", date(2024, 2, 10), date(2024, 3, 11), date(2024, 3, 11), 165000, False, False),
    ("Neuland Traders", "NEU-540", date(2024, 2, 27), date(2024, 3, 28), date(2024, 3, 27), 175000, False, False),
    ("Neuland Traders", "NEU-556", date(2024, 3, 12), date(2024, 4, 11), date(2024, 4, 10), 190000, False, False),
    ("Neuland Traders", "NEU-570", date(2024, 3, 28), date(2024, 4, 27), date(2024, 4, 28), 160000, False, False),
    ("Neuland Traders", "NEU-585", date(2024, 4, 9), date(2024, 5, 9), date(2024, 5, 8), 200000, False, False),
    ("Neuland Traders", "NEU-598", date(2024, 4, 24), date(2024, 5, 24), date(2024, 5, 25), 155000, False, False),
    ("Neuland Traders", "NEU-612", date(2024, 5, 11), date(2024, 6, 10), date(2024, 6, 11), 210000, False, False),
    ("Neuland Traders", "NEU-625", date(2024, 5, 27), date(2024, 6, 26), date(2024, 6, 24), 170000, False, False),
    ("Neuland Traders", "NEU-640", date(2024, 6, 9), date(2024, 7, 9), date(2024, 7, 9), 195000, False, False),
    ("Neuland Traders", "NEU-655", date(2024, 6, 26), date(2024, 7, 26), date(2024, 7, 27), 180000, False, False),

    # --- Sunrise Pharma Corp: stable ~35-37d, 2 disputes, 1 credit note
    ("Sunrise Pharma Corp", "SUN-201", date(2024, 1, 10), date(2024, 2, 9), date(2024, 2, 15), 420000, False, False),
    ("Sunrise Pharma Corp", "SUN-214", date(2024, 1, 26), date(2024, 2, 25), date(2024, 3, 3), 380000, False, True),
    ("Sunrise Pharma Corp", "SUN-229", date(2024, 2, 12), date(2024, 3, 13), date(2024, 3, 18), 310000, False, False),
    ("Sunrise Pharma Corp", "SUN-CN-05", date(2024, 2, 15), date(2024, 3, 16), None, 45000, True, False),
    ("Sunrise Pharma Corp", "SUN-241", date(2024, 2, 28), date(2024, 3, 29), date(2024, 4, 2), 295000, False, False),
    ("Sunrise Pharma Corp", "SUN-256", date(2024, 3, 14), date(2024, 4, 13), date(2024, 4, 19), 340000, False, False),
    ("Sunrise Pharma Corp", "SUN-270", date(2024, 3, 29), date(2024, 4, 28), date(2024, 5, 5), 260000, False, True),
    ("Sunrise Pharma Corp", "SUN-284", date(2024, 4, 11), date(2024, 5, 11), date(2024, 5, 16), 315000, False, False),
    ("Sunrise Pharma Corp", "SUN-299", date(2024, 4, 26), date(2024, 5, 26), date(2024, 6, 1), 275000, False, False),
    ("Sunrise Pharma Corp", "SUN-312", date(2024, 5, 13), date(2024, 6, 12), date(2024, 6, 19), 330000, False, False),
    ("Sunrise Pharma Corp", "SUN-326", date(2024, 5, 29), date(2024, 6, 28), date(2024, 7, 4), 290000, False, False),
    ("Sunrise Pharma Corp", "SUN-340", date(2024, 6, 10), date(2024, 7, 10), date(2024, 7, 16), 305000, False, False),
    ("Sunrise Pharma Corp", "SUN-355", date(2024, 6, 27), date(2024, 7, 27), date(2024, 8, 2), 260000, False, False),

    # --- Kwality Distributors: stable payer, 2 invoices still open at end of data
    ("Kwality Distributors", "KWA-801", date(2024, 1, 15), date(2024, 2, 14), date(2024, 2, 20), 220000, False, False),
    ("Kwality Distributors", "KWA-815", date(2024, 2, 2), date(2024, 3, 3), date(2024, 3, 10), 195000, False, False),
    ("Kwality Distributors", "KWA-830", date(2024, 2, 20), date(2024, 3, 21), date(2024, 3, 25), 240000, False, False),
    ("Kwality Distributors", "KWA-845", date(2024, 3, 8), date(2024, 4, 7), date(2024, 4, 14), 205000, False, False),
    ("Kwality Distributors", "KWA-860", date(2024, 3, 24), date(2024, 4, 23), date(2024, 5, 1), 230000, False, False),
    ("Kwality Distributors", "KWA-875", date(2024, 4, 10), date(2024, 5, 10), date(2024, 5, 18), 260000, False, False),
    ("Kwality Distributors", "KWA-890", date(2024, 4, 27), date(2024, 5, 27), date(2024, 6, 5), 215000, False, False),
    ("Kwality Distributors", "KWA-905", date(2024, 5, 14), date(2024, 6, 13), date(2024, 6, 22), 250000, False, False),
    ("Kwality Distributors", "KWA-920", date(2024, 5, 30), date(2024, 6, 29), date(2024, 7, 9), 235000, False, False),
    ("Kwality Distributors", "KWA-935", date(2024, 6, 12), date(2024, 7, 12), None, 275000, False, False),
    ("Kwality Distributors", "KWA-950", date(2024, 6, 28), date(2024, 7, 28), None, 260000, False, False),

    # --- Same company, invoiced under a slightly different legal name for
    # two months - exercises the Stage-1-condition-2 manual name-map
    # override. Left UNMAPPED, this would also look like a sparse
    # 2-invoice new customer, which is deliberate: it's the realistic way
    # a name-variant problem actually shows up.
    ("Kwality Distributors Pvt. Ltd.", "KWA-965", date(2024, 7, 10), date(2024, 8, 9), date(2024, 8, 5), 245000, False, False),
    ("Kwality Distributors Pvt. Ltd.", "KWA-980", date(2024, 7, 28), date(2024, 8, 27), None, 230000, False, False),

    # --- Vertex Pharma Retail: brand-new customer, exactly 2 invoices,
    # both in the same single calendar month - the "fewer than 2 invoices
    # in a window" sparse case named in Stage-1 condition 3.
    ("Vertex Pharma Retail", "VTX-01", date(2024, 7, 5), date(2024, 8, 4), date(2024, 7, 30), 95000, False, False),
    ("Vertex Pharma Retail", "VTX-02", date(2024, 7, 20), date(2024, 8, 19), None, 120000, False, False),

    # --- Bright Health Distributors: two invoices in January, then a
    # five-month gap, then two more in July - the "long gap in invoice
    # history" sparse case named in Stage-1 condition 3.
    ("Bright Health Distributors", "BRT-01", date(2024, 1, 10), date(2024, 2, 9), date(2024, 2, 1), 150000, False, False),
    ("Bright Health Distributors", "BRT-02", date(2024, 1, 25), date(2024, 2, 24), date(2024, 2, 15), 130000, False, False),
    ("Bright Health Distributors", "BRT-03", date(2024, 7, 8), date(2024, 8, 7), date(2024, 8, 5), 175000, False, False),
    ("Bright Health Distributors", "BRT-04", date(2024, 7, 22), date(2024, 8, 21), None, 140000, False, False),

    # --- Falcon Pharma Wholesale: consistently healthy payer, paired in
    # config/external_signals_template.csv with a VOLUNTARY rating
    # withdrawal (paid off debt, no longer needs a rating) - exercises
    # the "reviewed, not flagged" path end-to-end through the real report,
    # not just a standalone unit test of the scoring engine.
    ("Falcon Pharma Wholesale", "FAL-301", date(2024, 2, 6), date(2024, 3, 7), date(2024, 3, 2), 205000, False, False),
    ("Falcon Pharma Wholesale", "FAL-315", date(2024, 3, 4), date(2024, 4, 3), date(2024, 3, 29), 190000, False, False),
    ("Falcon Pharma Wholesale", "FAL-330", date(2024, 4, 9), date(2024, 5, 9), date(2024, 5, 4), 225000, False, False),
    ("Falcon Pharma Wholesale", "FAL-344", date(2024, 5, 6), date(2024, 6, 5), date(2024, 5, 30), 210000, False, False),
    ("Falcon Pharma Wholesale", "FAL-359", date(2024, 6, 3), date(2024, 7, 3), date(2024, 6, 28), 230000, False, False),
    ("Falcon Pharma Wholesale", "FAL-373", date(2024, 7, 1), date(2024, 7, 31), date(2024, 7, 26), 215000, False, False),
]

# Each row below is broken in exactly one way, so errors_df should show
# five distinct reasons after parsing.
_BROKEN_ROWS = [
    {"Client Name": "", "Inv No": "BAD-001", "Inv Dt": "05/07/2024", "Due Dt": "04/08/2024",
     "Paid On": "", "Amt (INR)": "150000", "CN?": "N", "Disputed?": "No"},  # missing customer_name
    {"Client Name": "Orchid Pharma Distributors", "Inv No": "BAD-002", "Inv Dt": "not a date",
     "Due Dt": "04/08/2024", "Paid On": "", "Amt (INR)": "150000", "CN?": "N", "Disputed?": "No"},  # bad invoice_date
    {"Client Name": "Sunrise Pharma Corp", "Inv No": "BAD-003", "Inv Dt": "10/07/2024",
     "Due Dt": "09/08/2024", "Paid On": "", "Amt (INR)": "TBD", "CN?": "N", "Disputed?": "No"},  # bad amount
    {"Client Name": "Neuland Traders", "Inv No": "", "Inv Dt": "12/07/2024", "Due Dt": "11/08/2024",
     "Paid On": "", "Amt (INR)": "180000", "CN?": "N", "Disputed?": "No"},  # missing invoice_id
    {"Client Name": "Kwality Distributors", "Inv No": "BAD-005", "Inv Dt": "15/07/2024",
     "Due Dt": "14/08/2024", "Paid On": "", "Amt (INR)": "200000", "CN?": "maybe", "Disputed?": "No"},  # bad CN? flag
]


def generate_synthetic_ledger(path: Path = OUTPUT_PATH) -> Path:
    rows = []
    for i, (customer, inv_id, inv_date, due_date, pay_date, amount, is_cn, is_disputed) in enumerate(_GOOD_ROWS):
        rows.append({
            "Client Name": customer,
            "Inv No": inv_id,
            "Inv Dt": _fmt_date(inv_date, i),
            "Due Dt": _fmt_date(due_date, i + 1),
            "Paid On": _fmt_date(pay_date, i + 2),
            "Amt (INR)": _fmt_amount(amount, i),
            "CN?": "Y" if is_cn else "N",
            "Disputed?": "Yes" if is_disputed else "No",
        })
    rows.extend(_BROKEN_ROWS)

    df = pd.DataFrame(rows, columns=COLUMNS)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path


if __name__ == "__main__":
    out = generate_synthetic_ledger()
    print(f"Wrote {out}")
