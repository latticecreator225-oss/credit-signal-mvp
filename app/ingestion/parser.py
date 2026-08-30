"""
Ledger parser: turns a messy, real-world AR-ledger export (CSV or Excel)
into the canonical schema the rest of the pipeline works on.

Design intent: real exports will have inconsistent column names and
date formats. Column matching is forgiving (exact alias match, then
fuzzy fallback). Row-level problems (a bad date, a non-numeric amount,
a blank customer name) are never silently dropped - they're quarantined
into `errors_df` with a reason, so nothing disappears without a trace.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from dateutil import parser as dateutil_parser
from rapidfuzz import fuzz

# --- canonical schema -------------------------------------------------

CANONICAL_COLUMNS = [
    "customer_name",
    "invoice_id",
    "invoice_date",
    "due_date",
    "payment_date",
    "invoice_amount",
    "credit_note_flag",
    "dispute_flag",
]

# A source file must have *some* column mappable to each of these, or we
# refuse the file outright (better than pretending to process a ledger
# that has no dates or amounts). payment_date/credit_note_flag/dispute_flag
# are allowed to be entirely absent - some exports won't track disputes at
# all - in which case we default them rather than rejecting the file.
REQUIRED_COLUMNS = {"customer_name", "invoice_id", "invoice_date", "due_date", "invoice_amount"}

OPTIONAL_COLUMNS = {"payment_date", "credit_note_flag", "dispute_flag"}

# Known aliases per canonical field, used for exact matching after
# normalization. Anything not caught here falls through to fuzzy matching
# against this same list, so it doesn't have to be exhaustive.
ALIASES: dict[str, list[str]] = {
    "customer_name": [
        "customer name", "customer", "client", "client name", "party", "party name",
        "debtor", "debtor name", "buyer", "buyer name", "account name", "cust name",
    ],
    "invoice_id": [
        "invoice id", "invoice no", "invoice number", "inv no", "bill no", "bill number",
        "inv ref", "invoice ref", "doc no", "document number",
    ],
    "invoice_date": [
        "invoice date", "inv date", "inv dt", "bill date", "bill dt", "doc date", "date",
    ],
    "due_date": [
        "due date", "due dt", "payment due", "payment due date",
    ],
    "payment_date": [
        "payment date", "paid date", "paid on", "pay date", "realisation date",
        "realization date", "receipt date", "cleared on", "settled date",
    ],
    "invoice_amount": [
        "invoice amount", "amount", "amt", "inv amount", "bill amount", "bill amt",
        "value", "invoice value", "gross amount", "total amount",
    ],
    "credit_note_flag": [
        "credit note flag", "credit note", "cn", "is credit note", "cn flag",
    ],
    "dispute_flag": [
        "dispute flag", "dispute", "disputed", "is disputed",
    ],
}

FUZZY_THRESHOLD = 65  # token_set_ratio score (0-100) required to accept a fuzzy column match

TRUE_STRINGS = {"true", "yes", "y", "1"}
FALSE_STRINGS = {"false", "no", "n", "0", "", "nan", "none"}

EMPTY_DATE_STRINGS = {"", "nan", "none", "nat", "n/a", "na", "tbd", "-"}

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")
_CURRENCY_PREFIX_RE = re.compile(r"(?i)^\s*(rs\.?|inr)\s*")


def _normalize(s: str) -> str:
    """lowercase, collapse to space-separated alnum tokens - keeps word
    boundaries so fuzzy token matching has something to work with."""
    s = re.sub(r"[^a-z0-9]+", " ", str(s).lower())
    return " ".join(s.split())


def match_columns(raw_columns: list[str]) -> tuple[dict[str, str], list[str]]:
    """
    Map each canonical field to the raw column that best represents it.

    Returns (mapping, unmatched_required) where mapping is
    {canonical_name: raw_column_name}, and unmatched_required lists any
    REQUIRED field with no plausible source column at all.
    """
    normalized_raw = {col: _normalize(col) for col in raw_columns}
    mapping: dict[str, str] = {}
    used_raw: set[str] = set()

    # pass 1: exact alias match
    for canonical, aliases in ALIASES.items():
        alias_set = {_normalize(a) for a in aliases} | {_normalize(canonical.replace("_", " "))}
        for raw_col, norm in normalized_raw.items():
            if raw_col in used_raw:
                continue
            if norm in alias_set:
                mapping[canonical] = raw_col
                used_raw.add(raw_col)
                break

    # pass 2: fuzzy fallback for anything still unmapped, scored against
    # every known alias (not just the canonical name) so abbreviations
    # like "Amt (INR)" still find "invoice_amount" via the "amt" alias.
    remaining_raw = [c for c in raw_columns if c not in used_raw]
    for canonical in CANONICAL_COLUMNS:
        if canonical in mapping or not remaining_raw:
            continue
        candidate_terms = [_normalize(canonical.replace("_", " "))]
        candidate_terms += [_normalize(a) for a in ALIASES.get(canonical, [])]

        best_score, best_raw = 0, None
        for raw_col in remaining_raw:
            norm = normalized_raw[raw_col]
            score = max(fuzz.token_set_ratio(norm, term) for term in candidate_terms)
            if score > best_score:
                best_score, best_raw = score, raw_col

        if best_raw is not None and best_score >= FUZZY_THRESHOLD:
            mapping[canonical] = best_raw
            used_raw.add(best_raw)
            remaining_raw.remove(best_raw)

    unmatched_required = sorted(REQUIRED_COLUMNS - set(mapping.keys()))
    return mapping, unmatched_required


def _parse_date(value) -> tuple[pd.Timestamp | None, str | None]:
    """Returns (parsed_timestamp_or_None, error_reason_or_None).
    A genuinely empty cell is (None, None) - that's fine, not an error
    (e.g. an unpaid invoice's payment_date). A cell with content that
    doesn't parse is (None, "unparseable date: ..."). """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None, None
    if isinstance(value, pd.Timestamp):
        return value, None
    s = str(value).strip()
    if s.lower() in EMPTY_DATE_STRINGS:
        return None, None
    # ISO (YYYY-MM-DD) is unambiguous - parse it directly rather than via
    # dateutil's dayfirst heuristic. dateutil applies dayfirst to *any*
    # ambiguous pair of components, not just the leading one - so
    # "2024-04-09" with dayfirst=True gets misread as day=04, month=09
    # (i.e. 9 September instead of 9 April) whenever both trailing
    # components are <=12. That's a silent, wrong-answer bug, not an
    # edge case worth leaving in.
    if _ISO_DATE_RE.match(s):
        try:
            return pd.Timestamp(s), None
        except (ValueError, OverflowError):
            return None, f"unparseable date: {s!r}"
    try:
        dt = dateutil_parser.parse(s, dayfirst=True, fuzzy=False)
        return pd.Timestamp(dt), None
    except (ValueError, OverflowError, TypeError):
        return None, f"unparseable date: {s!r}"


def _parse_amount(value) -> tuple[float | None, str | None]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None, "missing amount"
    if isinstance(value, (int, float)):
        return float(value), None
    s = str(value).strip()
    if s.lower() in {"", "nan", "none"}:
        return None, "missing amount"
    negative = s.startswith("(") and s.endswith(")")
    cleaned = _CURRENCY_PREFIX_RE.sub("", s)
    cleaned = re.sub(r"[₹$,\s()]", "", cleaned)
    if cleaned == "":
        return None, f"unparseable amount: {s!r}"
    try:
        amount = float(cleaned)
        return (-amount if negative else amount), None
    except ValueError:
        return None, f"unparseable amount: {s!r}"


def _parse_bool(value) -> bool | None:
    """Returns True/False, or None if the cell had content that isn't
    recognizable as either (caller treats that as a row error)."""
    if isinstance(value, bool):
        return value
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    s = str(value).strip().lower()
    if s in TRUE_STRINGS:
        return True
    if s in FALSE_STRINGS:
        return False
    return None


@dataclass
class ParseResult:
    clean_df: pd.DataFrame
    errors_df: pd.DataFrame
    column_mapping: dict[str, str]
    total_rows: int
    parsed_rows: int
    error_row_count: int
    source_columns: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Read {self.total_rows} rows from columns: {self.source_columns}",
            f"  Parsed cleanly : {self.parsed_rows}",
            f"  Quarantined    : {self.error_row_count}  (see .errors_df for reasons)",
            "Column mapping used:",
        ]
        for canonical in CANONICAL_COLUMNS:
            if canonical in self.column_mapping:
                lines.append(f"    {canonical:<18} <- \"{self.column_mapping[canonical]}\"")
            else:
                lines.append(f"    {canonical:<18} <- (not found in source; defaulted)")
        return "\n".join(lines)


def read_raw(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path, dtype=str)
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def parse_ledger_file(path: str | Path) -> ParseResult:
    raw_df = read_raw(path)
    raw_columns = list(raw_df.columns)
    mapping, unmatched_required = match_columns(raw_columns)

    if unmatched_required:
        raise ValueError(
            "Could not find a plausible source column for required field(s): "
            f"{', '.join(unmatched_required)}.\n"
            f"Source columns were: {raw_columns}\n"
            "Rename the source column(s), or add an alias for them in "
            "app/ingestion/parser.py's ALIASES table."
        )

    clean_rows: list[dict] = []
    error_rows: list[dict] = []

    for idx, row in raw_df.iterrows():
        reasons: list[str] = []

        customer_name = str(row[mapping["customer_name"]]).strip()
        if not customer_name or customer_name.lower() in {"nan", "none"}:
            reasons.append("missing customer_name")

        invoice_id = str(row[mapping["invoice_id"]]).strip()
        if not invoice_id or invoice_id.lower() in {"nan", "none"}:
            reasons.append("missing invoice_id")

        invoice_date, err = _parse_date(row[mapping["invoice_date"]])
        if invoice_date is None:
            reasons.append(err or "missing invoice_date")

        due_date, err = _parse_date(row[mapping["due_date"]])
        if due_date is None:
            reasons.append(err or "missing due_date")

        payment_date = None
        if "payment_date" in mapping:
            payment_date, err = _parse_date(row[mapping["payment_date"]])
            # a blank payment_date is an expected, valid state (unpaid
            # invoice) - only an actual unparseable value is an error.
            if payment_date is None and err is not None:
                reasons.append(err)

        amount, err = _parse_amount(row[mapping["invoice_amount"]])
        if amount is None:
            reasons.append(err or "missing invoice_amount")

        credit_note_flag = False
        if "credit_note_flag" in mapping:
            parsed = _parse_bool(row[mapping["credit_note_flag"]])
            if parsed is None:
                reasons.append(f"unparseable credit_note_flag: {row[mapping['credit_note_flag']]!r}")
            else:
                credit_note_flag = parsed

        dispute_flag = False
        if "dispute_flag" in mapping:
            parsed = _parse_bool(row[mapping["dispute_flag"]])
            if parsed is None:
                reasons.append(f"unparseable dispute_flag: {row[mapping['dispute_flag']]!r}")
            else:
                dispute_flag = parsed

        if reasons:
            error_rows.append({
                "source_row_number": idx + 2,  # 1-indexed + header row
                "reasons": "; ".join(reasons),
                **{col: row[col] for col in raw_columns},
            })
            continue

        clean_rows.append({
            "customer_name": customer_name,
            "invoice_id": invoice_id,
            "invoice_date": invoice_date,
            "due_date": due_date,
            "payment_date": payment_date,
            "invoice_amount": amount,
            "credit_note_flag": credit_note_flag,
            "dispute_flag": dispute_flag,
        })

    clean_df = pd.DataFrame(clean_rows, columns=CANONICAL_COLUMNS)
    if not clean_df.empty:
        clean_df["invoice_date"] = pd.to_datetime(clean_df["invoice_date"])
        clean_df["due_date"] = pd.to_datetime(clean_df["due_date"])
        clean_df["payment_date"] = pd.to_datetime(clean_df["payment_date"])
        clean_df["is_paid"] = clean_df["payment_date"].notna()

    errors_df = pd.DataFrame(error_rows)

    return ParseResult(
        clean_df=clean_df,
        errors_df=errors_df,
        column_mapping=mapping,
        total_rows=len(raw_df),
        parsed_rows=len(clean_df),
        error_row_count=len(errors_df),
        source_columns=raw_columns,
    )
