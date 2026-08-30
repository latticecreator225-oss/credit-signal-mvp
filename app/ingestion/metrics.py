"""
Per-customer, per-month metrics computed from a cleaned ledger
(the `clean_df` produced by app.ingestion.parser.parse_ledger_file).

Per the Stage 1 scoping decisions:
  - days-to-pay is computed BOTH ways: invoice_date -> payment_date
    (cycle time - the primary metric, matches standard DSO convention)
    and due_date -> payment_date (lateness relative to agreed terms,
    kept as a secondary column).
  - credit notes REDUCE exposure (a credit-note row's amount is
    subtracted from that customer's outstanding balance, and excluded
    from "invoiced" totals as a positive figure).
"""
from __future__ import annotations

import pandas as pd

from app.config import ROLLING_TREND_WINDOW_MONTHS, ROLLING_TREND_MAX_GAP_MONTHS


def compute_monthly_metrics(clean_df: pd.DataFrame) -> pd.DataFrame:
    """
    One row per (customer_name, invoice_month). invoice_month is the
    calendar month the invoice was RAISED in, not paid in - this keeps
    every invoice attributed to a single stable cohort even if payment
    lands in a later month, which is what a "did behaviour drift" trend
    needs (grouping by payment month would let a single slow payment
    silently vanish from one cohort and inflate another).
    """
    if clean_df.empty:
        return pd.DataFrame(columns=[
            "customer_name", "invoice_month", "invoice_count", "dispute_count",
            "credit_note_count", "net_invoiced", "dispute_rate", "credit_note_rate",
            "dispute_or_cn_rate", "avg_days_to_pay_invoice", "avg_days_to_pay_due",
            "settled_invoice_count",
        ])

    df = clean_df.copy()
    df["invoice_month"] = df["invoice_date"].dt.to_period("M")
    # credit notes subtract from what's owed rather than adding to it
    df["net_amount"] = df["invoice_amount"].where(~df["credit_note_flag"], -df["invoice_amount"])

    settled = df[df["is_paid"] & ~df["credit_note_flag"]].copy()
    settled["days_to_pay_invoice"] = (settled["payment_date"] - settled["invoice_date"]).dt.days
    settled["days_to_pay_due"] = (settled["payment_date"] - settled["due_date"]).dt.days

    dtp = (
        settled.groupby(["customer_name", "invoice_month"])
        .agg(
            avg_days_to_pay_invoice=("days_to_pay_invoice", "mean"),
            avg_days_to_pay_due=("days_to_pay_due", "mean"),
            settled_invoice_count=("invoice_id", "count"),
        )
        .reset_index()
    )

    counts = (
        df.groupby(["customer_name", "invoice_month"])
        .agg(
            invoice_count=("invoice_id", "count"),
            dispute_count=("dispute_flag", "sum"),
            credit_note_count=("credit_note_flag", "sum"),
            net_invoiced=("net_amount", "sum"),
        )
        .reset_index()
    )
    counts["dispute_rate"] = counts["dispute_count"] / counts["invoice_count"]
    counts["credit_note_rate"] = counts["credit_note_count"] / counts["invoice_count"]
    # combined view used by Stage 3 scoring, which treats "dispute/credit-note
    # frequency" as one signal per the MVP brief, not two
    counts["dispute_or_cn_rate"] = (
        (counts["dispute_count"] + counts["credit_note_count"]) / counts["invoice_count"]
    )

    monthly = counts.merge(dtp, on=["customer_name", "invoice_month"], how="left")
    return monthly.sort_values(["customer_name", "invoice_month"]).reset_index(drop=True)


def compute_rolling_trend(
    monthly_df: pd.DataFrame,
    window: int = ROLLING_TREND_WINDOW_MONTHS,
    max_gap_months: int = ROLLING_TREND_MAX_GAP_MONTHS,
) -> pd.DataFrame:
    """
    Per customer: average of the most recent `window` months-with-activity
    vs. the `window` months before that, for days-to-pay, dispute rate,
    and the combined dispute-or-credit-note rate.

    `trend_data_quality` records one of three states, and the pct-change
    columns are only ever populated when it's "ok":
      - "gap_exceeds_threshold": somewhere within the months actually
        being compared, the customer went more than `max_gap_months`
        months between invoices. Averaging across that gap wouldn't
        measure a behaviour change, it'd mash two unrelated snapshots
        together - checked BEFORE the depth check below, because a
        customer can have "enough months" of history that are nowhere
        near each other in time (2 months of history 6 months apart is
        not the same situation as 2 consecutive months).
      - "too_few_invoices": no gap problem, but there isn't `window`
        months of prior history to compare against yet (a genuinely new
        customer).
      - "ok": neither problem - the comparison is computed normally.
    """
    empty_columns = [
        "customer_name", "months_of_history", "trend_data_quality",
        "recent_avg_days_to_pay", "prior_avg_days_to_pay", "days_to_pay_pct_change",
        "recent_dispute_rate", "prior_dispute_rate", "dispute_rate_pct_change",
        "recent_dispute_or_cn_rate", "prior_dispute_or_cn_rate", "dispute_or_cn_rate_pct_change",
    ]
    if monthly_df.empty:
        return pd.DataFrame(columns=empty_columns)

    def _pct_change(recent_val, prior_val):
        if prior_val is None or pd.isna(prior_val) or prior_val == 0:
            return None
        return (recent_val - prior_val) / prior_val * 100

    rows = []
    for customer, g in monthly_df.sort_values("invoice_month").groupby("customer_name"):
        g = g.reset_index(drop=True)
        n = len(g)
        recent = g.iloc[max(0, n - window):]
        prior = g.iloc[max(0, n - 2 * window):max(0, n - window)]

        # gap check: the largest jump (in months) between consecutive
        # data points across the whole span actually being compared.
        combined = pd.concat([prior, recent]).sort_values("invoice_month")
        ordinals = combined["invoice_month"].apply(lambda p: p.ordinal)
        gaps = ordinals.diff().dropna()
        max_gap = int(gaps.max()) if len(gaps) else 0

        if max_gap > max_gap_months:
            quality = "gap_exceeds_threshold"
        elif len(prior) == 0:
            quality = "too_few_invoices"
        else:
            quality = "ok"

        recent_dtp = recent["avg_days_to_pay_invoice"].mean()
        prior_dtp = prior["avg_days_to_pay_invoice"].mean() if len(prior) else None
        recent_dispute = recent["dispute_rate"].mean()
        prior_dispute = prior["dispute_rate"].mean() if len(prior) else None
        recent_dcn = recent["dispute_or_cn_rate"].mean()
        prior_dcn = prior["dispute_or_cn_rate"].mean() if len(prior) else None

        if quality == "ok":
            dtp_change = _pct_change(recent_dtp, prior_dtp)
            dispute_change = _pct_change(recent_dispute, prior_dispute)
            dcn_change = _pct_change(recent_dcn, prior_dcn)
        else:
            dtp_change = None
            dispute_change = None
            dcn_change = None

        rows.append({
            "customer_name": customer,
            "months_of_history": n,
            "trend_data_quality": quality,
            "recent_avg_days_to_pay": recent_dtp,
            "prior_avg_days_to_pay": prior_dtp,
            "days_to_pay_pct_change": dtp_change,
            "recent_dispute_rate": recent_dispute,
            "prior_dispute_rate": prior_dispute,
            "dispute_rate_pct_change": dispute_change,
            "recent_dispute_or_cn_rate": recent_dcn,
            "prior_dispute_or_cn_rate": prior_dcn,
            "dispute_or_cn_rate_pct_change": dcn_change,
        })
    return pd.DataFrame(rows, columns=empty_columns)


def compute_exposure(clean_df: pd.DataFrame, as_of=None) -> pd.DataFrame:
    """
    Outstanding exposure per customer as of a given date (defaults to
    the latest date present anywhere in the ledger). An invoice counts
    as outstanding if it was raised on/before `as_of` and either has no
    payment yet, or was paid *after* `as_of`. Credit notes subtract
    from exposure.

    Every customer present anywhere in the ledger gets a row, including
    ones currently at exactly 0 - a fully-settled customer and a
    customer with no relationship on record are different facts, and
    silently omitting the former made them indistinguishable.
    """
    if clean_df.empty:
        return pd.DataFrame(columns=["customer_name", "outstanding_exposure", "as_of_date"])

    df = clean_df.copy()
    if as_of is None:
        as_of = pd.concat([df["invoice_date"], df["payment_date"]]).max()
    as_of = pd.Timestamp(as_of)

    df["net_amount"] = df["invoice_amount"].where(~df["credit_note_flag"], -df["invoice_amount"])
    is_outstanding = (df["invoice_date"] <= as_of) & (
        df["payment_date"].isna() | (df["payment_date"] > as_of)
    )
    # zero out non-outstanding rows rather than filtering them out, then
    # group over the WHOLE ledger - so a customer whose every invoice is
    # settled still gets a group (summing to 0), instead of vanishing.
    df["outstanding_amount"] = df["net_amount"].where(is_outstanding, 0.0)
    exposure = (
        df.groupby("customer_name")["outstanding_amount"]
        .sum()
        .reset_index()
        .rename(columns={"outstanding_amount": "outstanding_exposure"})
    )
    exposure["as_of_date"] = as_of
    return exposure.sort_values("outstanding_exposure", ascending=False).reset_index(drop=True)
