"""
Transparent, explainable weighted scoring. No ML, no black box: every
point on the 0-100 score traces back to one named signal and one weight
in app/config.py, and the evidence sentence lists exactly what fired.

The score is secondary. The evidence sentence is what a credit
controller actually acts on - per the MVP brief, this function is
written to make that sentence correct and honest, not to make the
number impressive.

Two signal families, kept visibly distinct in the output:
  - externally-backtested (Stage 2 signals_df): rating actions,
    litigation, auditor resignation, regulatory action, filing gaps.
    Rating action is the one with real (if thin) backtest evidence -
    weighted highest. The rest are plausible but not backtested the
    same rigorous way.
  - internal, UNVALIDATED (Stage 1 rolling_trend): DSO drift and
    dispute/credit-note frequency. Computed directly from the ledger,
    never checked against an actual outcome. Every evidence sentence
    these produce is prefixed "[unvalidated]" - that prefix is not
    cosmetic, don't remove it when wiring this into a report.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from app.config import (
    SCORE_WEIGHTS, SCORE_CAP, DSO_DRIFT_PCT_THRESHOLD, DISPUTE_CN_RATE_PCT_THRESHOLD,
)


@dataclass
class CustomerScore:
    customer_name: str
    score: int
    coverage_status: str
    fired_signals: list[str] = field(default_factory=list)
    evidence_sentences: list[str] = field(default_factory=list)
    unvalidated_signals_fired: list[str] = field(default_factory=list)
    # Signals that were checked and deliberately NOT scored (e.g. a benign
    # rating withdrawal) - tracked separately from evidence_sentences so a
    # report can surface "we looked and chose not to flag this" as its own
    # trust-building line, rather than string-matching evidence text for it.
    reviewed_not_flagged: list[str] = field(default_factory=list)

    @property
    def evidence_text(self) -> str:
        return " ".join(self.evidence_sentences) if self.evidence_sentences else "No flagged signals."


def _fmt_month(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    ts = pd.Timestamp(value)
    if pd.isna(ts):
        return ""
    return ts.strftime("%B %Y")


def _get(row, key, default=None):
    """row may be a pandas Series or None - one null-safe accessor for both."""
    if row is None:
        return default
    value = row.get(key, default)
    return default if (value is None or (isinstance(value, float) and pd.isna(value))) else value


def score_customer(
    customer_name: str,
    coverage_status: str,
    signal_row: pd.Series | None,
    trend_row: pd.Series | None,
) -> CustomerScore:
    points = 0
    fired: list[str] = []
    evidence: list[str] = []
    unvalidated_fired: list[str] = []
    reviewed_not_flagged: list[str] = []

    # --- externally-backtested signals (Stage 2) -------------------------
    rating_action = _get(signal_row, "rating_action", "none")
    if rating_action in ("downgrade", "withdrawal_non_cooperation"):
        points += SCORE_WEIGHTS["rating_downgrade_or_noncoop_withdrawal"]
        fired.append("rating_downgrade_or_noncoop_withdrawal")
        label = "downgraded" if rating_action == "downgrade" else "withdrawn (non-cooperation)"
        when = _fmt_month(_get(signal_row, "rating_action_date"))
        evidence.append(f"Rating {label}{' ' + when if when else ''}.")
    elif rating_action == "withdrawal_benign":
        # explicitly NOT scored: a company that paid off debt and no
        # longer needs a rating is not a risk signal. Named here so
        # it's visibly a decision, not a silent gap - and tracked
        # separately so a report can show "reviewed, not flagged" even
        # for a customer whose score is otherwise 0.
        when = _fmt_month(_get(signal_row, "rating_action_date"))
        note = f"Rating voluntarily withdrawn{' ' + when if when else ''} (debt repaid) - reviewed, not scored as a risk signal."
        evidence.append(note)
        reviewed_not_flagged.append(note)

    if _get(signal_row, "litigation_filed"):
        lit_type = _get(signal_row, "litigation_type")
        when = _fmt_month(_get(signal_row, "litigation_date"))
        if lit_type == "ibc_cirp":
            points += SCORE_WEIGHTS["ibc_cirp_litigation"]
            fired.append("ibc_cirp_litigation")
            evidence.append(f"IBC/NCLT-CIRP petition filed{' ' + when if when else ''}.")
        else:
            points += SCORE_WEIGHTS["civil_litigation"]
            fired.append("civil_litigation")
            evidence.append(f"Civil litigation filed{' ' + when if when else ''}.")

    if _get(signal_row, "auditor_resigned"):
        points += SCORE_WEIGHTS["auditor_resignation"]
        fired.append("auditor_resignation")
        when = _fmt_month(_get(signal_row, "auditor_resignation_date"))
        evidence.append(f"Statutory auditor resigned{' ' + when if when else ''}.")

    if _get(signal_row, "regulatory_action"):
        points += SCORE_WEIGHTS["regulatory_action"]
        fired.append("regulatory_action")
        when = _fmt_month(_get(signal_row, "regulatory_action_date"))
        note = _get(signal_row, "regulatory_action_note", "") or ""
        note_txt = f" ({note})" if note else ""
        evidence.append(f"Regulatory action{' ' + when if when else ''}{note_txt}.")

    if _get(signal_row, "filing_gap_12mo"):
        points += SCORE_WEIGHTS["filing_gap_12mo"]
        fired.append("filing_gap_12mo")
        evidence.append("No statutory filings on record for 12+ months.")

    # --- internal, UNVALIDATED signals (Stage 1) -------------------------
    quality = _get(trend_row, "trend_data_quality")
    dtp_change = _get(trend_row, "days_to_pay_pct_change")
    if quality == "ok" and dtp_change is not None and dtp_change > DSO_DRIFT_PCT_THRESHOLD:
        points += SCORE_WEIGHTS["dso_drift_unvalidated"]
        fired.append("dso_drift_unvalidated")
        unvalidated_fired.append("dso_drift_unvalidated")
        recent = _get(trend_row, "recent_avg_days_to_pay")
        prior = _get(trend_row, "prior_avg_days_to_pay")
        if recent is not None and prior is not None:
            evidence.append(
                f"[unvalidated] Payment terms drifted from {prior:.0f} to {recent:.0f} days "
                f"over the past quarter."
            )
        else:
            evidence.append(f"[unvalidated] Days-to-pay increased {dtp_change:.0f}% over the past quarter.")

    dcn_change = _get(trend_row, "dispute_or_cn_rate_pct_change")
    if quality == "ok" and dcn_change is not None and dcn_change > DISPUTE_CN_RATE_PCT_THRESHOLD:
        points += SCORE_WEIGHTS["dispute_cn_frequency_unvalidated"]
        fired.append("dispute_cn_frequency_unvalidated")
        unvalidated_fired.append("dispute_cn_frequency_unvalidated")
        evidence.append("[unvalidated] Dispute/credit-note frequency increased sharply over the past quarter.")

    if quality is not None and quality != "ok" and _get(trend_row, "months_of_history", 0):
        reason = "a gap in invoice history" if quality == "gap_exceeds_threshold" else "too few months of history"
        evidence.append(f"[internal payment-trend not computed: {reason}]")

    score = min(points, SCORE_CAP)
    return CustomerScore(
        customer_name=customer_name,
        score=score,
        coverage_status=coverage_status,
        fired_signals=fired,
        evidence_sentences=evidence,
        unvalidated_signals_fired=unvalidated_fired,
        reviewed_not_flagged=reviewed_not_flagged,
    )


def score_all_customers(
    ledger_customers: list[str],
    coverage_df: pd.DataFrame,
    signals_df: pd.DataFrame,
    trend_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Scores every customer in the ledger - including unrated and
    not-yet-researched ones. Coverage status rides along in the output
    so a downstream report can rank/display rated customers separately,
    per the MVP brief - this function does not itself decide who gets
    left out of a ranked list, it just refuses to pretend a rating
    signal fired when there was never a rating to check.
    """
    coverage_by_customer = (
        coverage_df.set_index("customer_name")["coverage_status"].to_dict()
        if not coverage_df.empty else {}
    )
    signals_by_customer = (
        signals_df.drop_duplicates("customer_name", keep="last").set_index("customer_name")
        if not signals_df.empty else pd.DataFrame()
    )
    trend_by_customer = (
        trend_df.drop_duplicates("customer_name", keep="last").set_index("customer_name")
        if not trend_df.empty else pd.DataFrame()
    )

    results = []
    for customer in ledger_customers:
        coverage_status = coverage_by_customer.get(customer, "not_yet_researched")
        signal_row = (
            signals_by_customer.loc[customer]
            if customer in getattr(signals_by_customer, "index", []) else None
        )
        trend_row = (
            trend_by_customer.loc[customer]
            if customer in getattr(trend_by_customer, "index", []) else None
        )
        cs = score_customer(customer, coverage_status, signal_row, trend_row)
        results.append({
            "customer_name": cs.customer_name,
            "score": cs.score,
            "coverage_status": cs.coverage_status,
            "fired_signals": ", ".join(cs.fired_signals) if cs.fired_signals else "(none)",
            "unvalidated_signals_fired": ", ".join(cs.unvalidated_signals_fired) if cs.unvalidated_signals_fired else "",
            "evidence": cs.evidence_text,
            "reviewed_not_flagged": " ".join(cs.reviewed_not_flagged) if cs.reviewed_not_flagged else "",
        })

    return pd.DataFrame(results).sort_values("score", ascending=False).reset_index(drop=True)
