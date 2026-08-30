"""
Central place for the tunable numbers this pipeline uses, so they can be
adjusted per-engagement or as real client ledgers get seen, without
hunting through logic code. Deliberately plain Python constants, not a
YAML/env-var system - this is a single-operator tool, not something
that needs runtime reconfiguration across environments.
"""

# --- rolling trend (app/ingestion/metrics.py) ---------------------------

# Window size, in months-with-invoice-activity, for the "recent" vs
# "prior" comparison.
ROLLING_TREND_WINDOW_MONTHS = 3

# If the gap between two consecutive invoice-months within the window
# being compared exceeds this many months, the trend comparison is
# withheld entirely (trend_data_quality = "gap_exceeds_threshold")
# rather than averaging across unrelated snapshots. This is exactly the
# kind of number that may need adjusting once a real client's ledger
# (with real, messier gaps) has been seen.
ROLLING_TREND_MAX_GAP_MONTHS = 3


# --- Stage 3 scoring (app/scoring/engine.py) -----------------------------

# Points awarded when each signal fires, summed per customer and capped
# at SCORE_CAP. Rating-agency action is weighted highest because it's
# the ONE signal with real backtest evidence behind it (1 confirmed
# clean hit out of 9 failures checked, 0 confirmed false positives out
# of 5 matched healthy controls). Litigation/auditor/regulatory/filing-gap
# are plausible but were not backtested the same rigorous way. The last
# two (DSO drift, dispute/credit-note frequency) are internal signals
# that have NOT been backtested at all - kept at the lowest weights and
# labeled "unvalidated" everywhere they appear in output, per the MVP
# brief.
SCORE_WEIGHTS = {
    "rating_downgrade_or_noncoop_withdrawal": 40,
    "ibc_cirp_litigation": 30,
    "civil_litigation": 12,
    "auditor_resignation": 18,
    "regulatory_action": 18,
    "filing_gap_12mo": 15,
    "dso_drift_unvalidated": 10,
    "dispute_cn_frequency_unvalidated": 8,
}

SCORE_CAP = 100

# Internal-signal firing thresholds. DSO drift's ">40%" comes directly
# from the MVP brief. The dispute/credit-note threshold has no backtest
# behind it at all (there was nothing to backtest it against) - it's a
# starting guess, flagged as such, not a measured number.
DSO_DRIFT_PCT_THRESHOLD = 40
DISPUTE_CN_RATE_PCT_THRESHOLD = 50
