"""
Manual customer-name normalization.

Deliberately NOT automatic/fuzzy matching. Merging "Orchid Pharma Ltd"
and "Orchid Pharma Limited" is probably right; merging two genuinely
different companies that happen to share a name fragment would corrupt
exposure and payment-history numbers in a way that's hard to notice
after the fact. A human reviews the raw names once per engagement and
fills in a small CSV; that mapping is applied before any metric is
computed.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = {"raw_name", "canonical_name"}


def load_name_map(path: str | Path) -> dict[str, str]:
    """A missing file is treated as "no overrides yet" (empty dict),
    not an error - this stays optional until a human has reviewed one
    engagement's customer list."""
    path = Path(path)
    if not path.exists():
        return {}

    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df.columns = [c.strip().lower() for c in df.columns]
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"{path} must have columns {sorted(REQUIRED_COLUMNS)}, "
            f"found: {list(df.columns)}"
        )

    name_map: dict[str, str] = {}
    for _, row in df.iterrows():
        raw = row["raw_name"].strip()
        canonical = row["canonical_name"].strip()
        if raw and canonical:
            name_map[raw] = canonical
    return name_map


def apply_name_map(clean_df: pd.DataFrame, name_map: dict[str, str]) -> tuple[pd.DataFrame, dict]:
    """
    Returns (df_with_canonical_names, report). The report exists so a
    stale or mistyped override doesn't fail silently in either
    direction:
      - mapped           : raw names that WERE found in the ledger and renamed
      - unmapped         : raw names in the ledger with no override entry
                            (not an error - most customers won't need one -
                            but worth a human's eyes before real client use)
      - unused_overrides : raw_names listed in the override file that never
                            appeared in this ledger (likely stale or a typo
                            in the override file itself)
    """
    df = clean_df.copy()
    if df.empty:
        return df, {"mapped": [], "unmapped": [], "unused_overrides": sorted(name_map.keys())}

    ledger_names = set(df["customer_name"].unique())
    mapped_names = ledger_names & set(name_map.keys())
    unmapped_names = ledger_names - set(name_map.keys())
    unused_overrides = set(name_map.keys()) - ledger_names

    df["customer_name"] = df["customer_name"].replace(name_map)

    report = {
        "mapped": sorted(mapped_names),
        "unmapped": sorted(unmapped_names),
        "unused_overrides": sorted(unused_overrides),
    }
    return df, report
