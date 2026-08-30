"""
Coverage screen: before anything is scored, every customer is classified
by whether this tool's strongest evidence - rating-agency actions -
even applies to them.

This isn't a formality. It's the central finding the backtest produced:
the rating-action signal only exists to be DETECTED for companies that
carry a public rating in the first place. A customer with no rating
history must never look "low risk" by default just because nothing
fired for them - there was nothing to fire.
"""
from __future__ import annotations

import pandas as pd

RATED = "rated"
UNRATED = "unrated"
NOT_YET_RESEARCHED = "not_yet_researched"


def build_coverage_screen(ledger_customers: list[str], signals_df: pd.DataFrame) -> pd.DataFrame:
    """
    One row per customer that appears in the AR ledger, in one of three
    states - not two:

      - "rated"              : has_public_rating == True in signals_df.
      - "unrated"             : has_public_rating == False - someone
                                researched this customer and confirmed
                                no public rating exists.
      - "not_yet_researched" : no row for this customer in signals_df at
                                all (nobody has looked yet), OR their
                                has_public_rating cell was blank/unparseable.
                                Deliberately NOT folded into "unrated":
                                "confirmed no rating" and "haven't
                                checked" are different facts, and must
                                not read the same in a report someone is
                                paying for.
    """
    if signals_df.empty:
        index = pd.Index([], name="customer_name")
    else:
        index = signals_df.drop_duplicates("customer_name", keep="last").set_index("customer_name").index

    rows = []
    for customer in sorted(set(ledger_customers)):
        if customer not in index:
            rows.append({"customer_name": customer, "coverage_status": NOT_YET_RESEARCHED})
            continue
        has_rating = signals_df.loc[
            signals_df["customer_name"] == customer, "has_public_rating"
        ].iloc[-1]
        # NOTE: cannot use `is True` / `is False` here. When a column has
        # no None values mixed in, pandas gives it a clean bool dtype,
        # and .iloc[] on that returns numpy.bool_ - a different object
        # from Python's True/False, so `is True` silently evaluates to
        # False even when the value IS true. (Ironically, the earlier
        # Stage 3 test of this exact pattern passed only because that
        # test data had a malformed row forcing object dtype, which
        # happens to preserve real Python bool - a false negative that
        # masked this until cleaner data exposed it.) pd.isna() first,
        # then plain truthiness, sidesteps the identity trap entirely.
        if pd.isna(has_rating):
            status = NOT_YET_RESEARCHED
        elif has_rating:
            status = RATED
        else:
            status = UNRATED
        rows.append({"customer_name": customer, "coverage_status": status})

    return pd.DataFrame(rows)
