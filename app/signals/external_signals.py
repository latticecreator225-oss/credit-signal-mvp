"""
External risk-signal data per customer: rating actions, litigation,
auditor resignation, sector-specific regulatory action, and statutory
filing gaps.

The only loader today is `load_from_csv` - a human fills in a template
per engagement, since there's no live Probe42/Karza connection yet.
The canonical DataFrame this returns is deliberately the contract for
everything downstream (the coverage screen, Stage 3 scoring): a future
`load_from_api(...)` would return the same shape, and nothing else in
the pipeline would need to change.

Design note carried over from the backtest: `has_public_rating` is a
SEPARATE field from `rating_action`, on purpose. "This customer has a
stable CRISIL A- that hasn't moved" (rated, action=none) and "nobody
has ever rated this customer" (unrated) are both "action=none" but are
completely different facts for the coverage screen - collapsing them
into one field would have silently erased the backtest's central
finding.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from dateutil import parser as dateutil_parser

CANONICAL_COLUMNS = [
    "customer_name",
    "has_public_rating",
    "rating_action",
    "rating_action_date",
    "litigation_filed",
    "litigation_date",
    "litigation_type",
    "auditor_resigned",
    "auditor_resignation_date",
    "regulatory_action",
    "regulatory_action_date",
    "regulatory_action_note",
    "filing_gap_12mo",
    "research_notes",
]

# withdrawal_benign (paid off debt, no longer needs a rating) and
# withdrawal_non_cooperation (agency gave up on the issuer) are kept as
# distinct values, not a single "withdrawal" - that distinction is the
# single most load-bearing finding from the backtest for avoiding false
# positives, and collapsing it here would defeat the point of Stage 3.
RATING_ACTIONS = {"none", "downgrade", "upgrade", "withdrawal_benign", "withdrawal_non_cooperation"}
LITIGATION_TYPES = {"", "ibc_cirp", "civil"}

YES_STRINGS = {"yes", "y", "true", "1"}
NO_STRINGS = {"no", "n", "false", "0"}


def _parse_yes_no(value, field_name: str, row_num: int, warnings: list[str]) -> bool | None:
    s = str(value).strip().lower()
    if s == "":
        # blank is a valid, expected state - "not yet checked" - not an
        # error, and (for has_public_rating specifically) NOT the same
        # fact as an explicit "no". Must return None here, before the
        # NO_STRINGS check, or coverage.py's documented "blank ->
        # not_yet_researched" behavior silently collapses into "unrated"
        # (blank used to match "" in NO_STRINGS and come back False).
        return None
    if s in YES_STRINGS:
        return True
    if s in NO_STRINGS:
        return False
    warnings.append(f"row {row_num}: unrecognized value {value!r} for {field_name} (expected yes/no) - left unknown")
    return None


def _parse_date_or_blank(value, field_name: str, row_num: int, warnings: list[str]):
    s = str(value).strip()
    if s == "" or s.lower() in {"nan", "none"}:
        return None
    try:
        return pd.Timestamp(dateutil_parser.parse(s, dayfirst=True, fuzzy=False))
    except (ValueError, OverflowError, TypeError):
        warnings.append(f"row {row_num}: unparseable date {value!r} for {field_name}")
        return None


def load_from_csv(path: str | Path) -> tuple[pd.DataFrame, list[str]]:
    """
    Returns (signals_df, warnings).

    A bad cell (unrecognized enum value, unparseable date) does NOT drop
    the row - this is manually-researched, per-engagement data a human
    is about to act on; silently discarding an otherwise-good row over
    one typo would be worse than flagging it and moving on. A row with
    no customer_name at all IS dropped, since there's nothing to attach
    it to, and that's recorded in warnings too.
    """
    path = Path(path)
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]

    missing_cols = set(CANONICAL_COLUMNS) - set(df.columns)
    if missing_cols:
        raise ValueError(
            f"{path} is missing required column(s): {sorted(missing_cols)}.\n"
            f"Expected columns: {CANONICAL_COLUMNS}"
        )

    warnings: list[str] = []
    rows = []
    for idx, row in df.iterrows():
        row_num = idx + 2
        customer = row["customer_name"].strip()
        if not customer:
            warnings.append(f"row {row_num}: missing customer_name - row skipped")
            continue

        has_rating = _parse_yes_no(row["has_public_rating"], "has_public_rating", row_num, warnings)

        rating_action = row["rating_action"].strip().lower()
        if rating_action and rating_action not in RATING_ACTIONS:
            warnings.append(
                f"row {row_num}: unrecognized rating_action {row['rating_action']!r} "
                f"(expected one of {sorted(RATING_ACTIONS)}) - treated as 'none'"
            )
            rating_action = "none"
        elif not rating_action:
            rating_action = "none"

        litigation_filed = _parse_yes_no(row["litigation_filed"], "litigation_filed", row_num, warnings)

        litigation_type = row["litigation_type"].strip().lower()
        if litigation_type not in LITIGATION_TYPES:
            warnings.append(
                f"row {row_num}: unrecognized litigation_type {row['litigation_type']!r} "
                f"(expected 'ibc_cirp' or 'civil') - left blank"
            )
            litigation_type = ""

        auditor_resigned = _parse_yes_no(row["auditor_resigned"], "auditor_resigned", row_num, warnings)
        regulatory_action = _parse_yes_no(row["regulatory_action"], "regulatory_action", row_num, warnings)
        filing_gap = _parse_yes_no(row["filing_gap_12mo"], "filing_gap_12mo", row_num, warnings)

        rows.append({
            "customer_name": customer,
            "has_public_rating": has_rating,
            "rating_action": rating_action,
            "rating_action_date": _parse_date_or_blank(row["rating_action_date"], "rating_action_date", row_num, warnings),
            "litigation_filed": litigation_filed,
            "litigation_date": _parse_date_or_blank(row["litigation_date"], "litigation_date", row_num, warnings),
            "litigation_type": litigation_type or None,
            "auditor_resigned": auditor_resigned,
            "auditor_resignation_date": _parse_date_or_blank(row["auditor_resignation_date"], "auditor_resignation_date", row_num, warnings),
            "regulatory_action": regulatory_action,
            "regulatory_action_date": _parse_date_or_blank(row["regulatory_action_date"], "regulatory_action_date", row_num, warnings),
            "regulatory_action_note": row["regulatory_action_note"].strip(),
            "filing_gap_12mo": filing_gap,
            "research_notes": row["research_notes"].strip(),
        })

    return pd.DataFrame(rows, columns=CANONICAL_COLUMNS), warnings
