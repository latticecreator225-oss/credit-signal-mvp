"""
Assembles the data a report template needs (scores, exposure, coverage)
into one plain dict - kept separate from Jinja2/PDF rendering so the
template layer doesn't need to know anything about pandas, and this
layer doesn't need to know anything about HTML.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

TOP_N_RANKED = 15

# The real numbers from the backtest this tool is built on. Not
# rounded up, not softened, not removed for a polished-looking sample -
# per explicit instruction, this text is the same in every report this
# tool generates, synthetic or real.
METHODOLOGY_TEXT = """
This tool is built on a manual backtest of 9 real Indian corporate failures and 5 matched \
healthy control companies (pharmaceutical manufacturing/distribution sector, 2017-2023). The \
finding: rating-agency actions (a downgrade, or a rating withdrawal specifically due to \
"issuer not cooperating") were the only signal that reliably discriminated between the two \
groups - present before failures, absent on every matched healthy control checked.

The honest numbers from that backtest: 1 confirmed, precisely-dated hit out of 9 failures \
checked, against 0 confirmed false positives out of 5 matched healthy controls. That is thin \
evidence by any normal statistical standard. It is a directional finding, not a validated \
model, and this tool does not claim otherwise anywhere in its scoring.

This signal only exists to be DETECTED for companies that carry a public credit rating in the \
first place. Customers with no rating history are structurally invisible to it - which is why \
this report separates "rated" customers (where the strongest evidence applies) from "unrated" \
and "not yet researched" customers (where it does not), rather than scoring everyone on one \
shared scale.

Litigation, auditor resignation, sector-specific regulatory action, and statutory filing gaps \
are scored because they are plausible, verifiable, public facts - but were not backtested with \
the same rigor as the rating-agency signal, and are weighted lower than it accordingly.

Internal signals computed from a customer's own payment history in this client's ledger - a \
rolling increase in days-to-pay, or in dispute/credit-note frequency - are explicitly \
UNVALIDATED. They were not part of the original backtest; there was no ledger data to test \
them against. They carry the lowest weights in this report's scoring, and every evidence line \
they produce is marked "[unvalidated]" for exactly this reason.
""".strip()


NEGATIVE_EXPOSURE_NOTE = (
    "A negative exposure balance (marked †) reflects an unlinked credit note that hasn't "
    "been offset against a specific invoice yet — not a rendering error."
)


def _fmt_currency(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    marker = " †" if value < 0 else ""
    return f"Rs. {value:,.0f}{marker}"


def build_report_context(
    scores_df: pd.DataFrame,
    exposure_df: pd.DataFrame,
    *,
    report_title: str,
    subtitle: str = "",
    disclaimer_banner: str | None = None,
    generated_at: datetime | None = None,
) -> dict:
    generated_at = generated_at or datetime.now()

    merged = scores_df.merge(
        exposure_df[["customer_name", "outstanding_exposure"]], on="customer_name", how="left"
    )
    merged["outstanding_exposure"] = merged["outstanding_exposure"].fillna(0.0)

    rated = merged[merged["coverage_status"] == "rated"].copy()
    unrated = merged[merged["coverage_status"] == "unrated"].copy()
    not_researched = merged[merged["coverage_status"] == "not_yet_researched"].copy()

    total_exposure = merged["outstanding_exposure"].sum()
    rated_exposure = rated["outstanding_exposure"].sum()
    out_of_coverage_exposure = unrated["outstanding_exposure"].sum() + not_researched["outstanding_exposure"].sum()
    # covers every value that could appear anywhere in the report (rows
    # and the aggregate sums derived from them - a sum can only go
    # negative if at least one row already did), so one flag is enough
    # to decide whether the † legend needs to render at all.
    has_negative_exposure = bool((merged["outstanding_exposure"] < 0).any())

    ranked = rated.sort_values("score", ascending=False).head(TOP_N_RANKED)

    # can in principle come from any coverage group, not just "rated" -
    # a benign withdrawal presupposes a company that once carried a
    # rating, which is the "rated" definition, but this is deliberately
    # not restricted to that group in case future signal types don't
    # share that constraint.
    reviewed_not_flagged = merged[merged["reviewed_not_flagged"].fillna("").str.len() > 0]

    unrated_and_unresearched = pd.concat([unrated, not_researched]).sort_values("customer_name")

    return {
        "report_title": report_title,
        "subtitle": subtitle,
        "disclaimer_banner": disclaimer_banner,
        "generated_at": generated_at.strftime("%d %B %Y"),
        "total_customers": len(merged),
        "rated_count": len(rated),
        "unrated_count": len(unrated),
        "not_researched_count": len(not_researched),
        "total_exposure": _fmt_currency(total_exposure),
        "rated_exposure": _fmt_currency(rated_exposure),
        "out_of_coverage_exposure": _fmt_currency(out_of_coverage_exposure),
        "has_negative_exposure": has_negative_exposure,
        "negative_exposure_note": NEGATIVE_EXPOSURE_NOTE,
        "ranked_customers": [
            {
                "rank": i + 1,
                "customer_name": row["customer_name"],
                "score": int(row["score"]),
                "exposure": _fmt_currency(row["outstanding_exposure"]),
                "evidence": row["evidence"],
            }
            for i, (_, row) in enumerate(ranked.iterrows())
        ],
        "reviewed_not_flagged": [
            {"customer_name": row["customer_name"], "note": row["reviewed_not_flagged"]}
            for _, row in reviewed_not_flagged.iterrows()
        ],
        "unrated_customers": [
            {
                "customer_name": row["customer_name"],
                "exposure": _fmt_currency(row["outstanding_exposure"]),
                "coverage_status": row["coverage_status"].replace("_", " "),
            }
            for _, row in unrated_and_unresearched.iterrows()
        ],
        "methodology_text": METHODOLOGY_TEXT,
    }
