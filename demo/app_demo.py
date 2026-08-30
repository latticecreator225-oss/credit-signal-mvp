"""
Streamlit wrapper around the existing AR-risk pipeline, for live sales
demos ONLY - not the delivery mechanism for real client engagements,
which stay local/script-based per the earlier decision.

Every function this app calls (parser, metrics, signals, coverage,
scoring, report builder) is imported unchanged from app/ - no pipeline
logic lives in this file, only Streamlit wiring and display.

Run with:
    venv\\Scripts\\streamlit run demo\\app_demo.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

# this file lives at demo/app_demo.py - one level below the project root
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from demo.data_generators.case_study_generator import generate_case_study_ledger
from app.ingestion.parser import parse_ledger_file
from app.ingestion.name_map import load_name_map, apply_name_map
from app.ingestion.metrics import compute_monthly_metrics, compute_rolling_trend, compute_exposure
from app.signals.external_signals import load_from_csv
from app.signals.coverage import build_coverage_screen
from app.scoring.engine import score_all_customers
from app.reporting.builder import build_report_context, METHODOLOGY_TEXT
from app.reporting.render import render_html

SIGNALS_PATH = PROJECT_ROOT / "demo" / "config" / "external_signals_template.csv"
CASE_STUDY_SIGNALS_PATH = PROJECT_ROOT / "demo" / "config" / "case_study_external_signals.csv"
NAME_MAP_PATH = PROJECT_ROOT / "demo" / "config" / "customer_name_map.csv"

CASE_STUDY_DISCLAIMER = (
    "Illustrative output, built from a public case study (Orchid Pharma, 2017) "
    "— not a live client engagement."
)

# --- per-section operator guidance -----------------------------------------
# Shown behind an ℹ️ popover next to each section header. The emphasis is
# deliberately on what a HUMAN has to do, because most of the signal data
# in this tool is researched and typed in by hand - there is no live API
# behind it yet, and a reader who assumes otherwise will misread the
# output.

MANUAL_STEPS: dict[str, str] = {
    "case_study": """
**Nothing to do here — this renders on open.** It's built from bundled data so it
works with no setup, which is what makes it safe to open cold on a call.

**What is real, and sourced:**
- CARE Ratings downgraded Orchid Pharma to **CARE D** on **18 April 2017**
- NCLT Chennai admitted Orchid Pharma into CIRP on **17 August 2017** — a ~4-month gap
- Neuland Laboratories as a size/sector-matched control (FY17 revenue ~₹579 Cr vs Orchid's ~₹683 Cr) that showed no adverse rating action

**What is illustrative:** every invoice-level number. No public AR ledger exists for
either company — the ledger is constructed to show what the *output* looks like
layered onto real external facts.

**If you ever edit this:** the data lives in `demo/config/case_study_external_signals.csv`.
Do not change the two real dates without re-checking the sources (Business Standard,
ICMAI casebook).
""",
    "upload": """
**Manual step 1 — export the ledger.** From the client's accounting system
(Tally / SAP / Zoho / Busy), export invoices as CSV or Excel. Minimum columns:
customer name, invoice number, invoice date, due date, payment date (blank if
unpaid), amount. Optional: credit-note flag, dispute flag.

**Column names do not need to match anything.** The parser fuzzy-matches headers —
`Client Name`, `Inv Dt`, `Amt (INR)` all resolve correctly — and handles several
different date formats mixed together in the same column.

**Demo discipline:** use clearly synthetic data on live calls. This uploader will
accept any file you point it at; nothing in the code stops you from loading a real
prospect's ledger, so that restraint is on you.
""",
    "parsing": """
**Manual step — review the quarantined rows.** Every row the parser couldn't read is
listed with a specific reason, never silently dropped. Open the expander, fix the
problem at source, re-upload. A non-zero quarantine count is normal for a real
export; ignoring it is not.

**Manual step — customer name variants.** Name matching is exact-string by design:
`Orchid Pharma Ltd` and `Orchid Pharma Limited` are treated as two different
customers. Automatic fuzzy merging was deliberately **not** built, because wrongly
merging two genuinely different companies corrupts exposure and payment history in a
way that's very hard to spot afterwards.

Instead: skim the customer list, then add rows to `demo/config/customer_name_map.csv` in
the form `raw_name,canonical_name`. That mapping is applied *before* any metric is
computed, and the run reports which overrides were used and which went unused (so a
typo in the override file doesn't fail silently).
""",
    "summary": """
**Nothing to fill in here — these are computed.** But the three coverage counts only
mean something if the research step was actually done: they come from
`demo/config/external_signals_template.csv`, not from any live data feed.

**How the exposure math works:**
- Credit notes **subtract** from what a customer owes.
- A customer at ₹0 still appears — "fully settled" and "no relationship on record"
  are different facts, and someone who just cleared a large balance is worth staying
  visible.
- A negative balance is marked **†** and footnoted: it means an unlinked credit note
  that hasn't been offset against a specific invoice yet, not a rendering error.
""",
    "ranked": """
**This is the section that carries the most manual work.** Every external signal below
was researched by hand and typed into `demo/config/external_signals_template.csv`. There
is no Probe42/Karza API wired up yet — that's a deliberate later step, not an
oversight.

**Where to look, per customer:**
- **Rating actions** — crisilratings.com, icra.in, careratings.com, indiaratings.co.in.
  Search the company, open the most recent rationale/press release.
- **IBC / NCLT-CIRP filings** — ibbi.gov.in (public CIRP list), nclt.gov.in orders.
  Record whether it's a CIRP filing or general civil litigation; they're weighted
  very differently.
- **Auditor resignation** — MCA Form ADT-3, or stock-exchange disclosures if listed.
- **Regulatory action** — CDSCO / state drug controller notices; FDA import alerts
  if the company exports.
- **Filing gap** — MCA master data: last AGM date, last balance sheet filed. 12+
  months dark counts as a signal in its own right.

**Always record the date, not just yes/no.** The date is the entire basis of any
lead-time claim you make to a buyer — a signal without a defensible date can't
support the pitch.

**Weights** live in `app/config.py` and are meant to be tuned, not treated as fixed.
""",
    "reviewed": """
**This section exists because one signal needs human judgment.** A withdrawn credit
rating is really two completely different facts:

- **Voluntary / benign** — the company repaid its debt and no longer needs a rating.
  This is **not** a risk signal. It scores zero.
- **Non-cooperation** — the agency gave up because the issuer stopped responding.
  This **is** a risk signal, weighted the same as a downgrade.

You have to open the agency's withdrawal notice and read which one it was, then
record either `withdrawal_benign` or `withdrawal_non_cooperation` in the signals CSV.

Confusing these two is the easiest way to produce a false positive on a healthy
company that simply refinanced — or to miss a real warning. Anything you mark benign
shows up here rather than disappearing, so the buyer can see the signal was noticed
and deliberately not flagged.
""",
    "uncovered": """
**The three-state distinction here is entirely manual, and it is the point of this
section.** Set it per customer via the `has_public_rating` column in
`demo/config/external_signals_template.csv`:

- `yes` → **rated**: you checked and found a public rating history.
- `no` → **unrated**: you checked and confirmed there is none.
- *(leave blank / no row)* → **not yet researched**: nobody has looked yet.

**Why this matters commercially:** the tool's one backtested signal is rating-agency
action, which structurally *cannot exist* for a company that carries no public
rating. So these customers are deliberately not scored and not ranked — a clean-looking
score here would be a fabricated reassurance.

Never let "not yet researched" get read as "low risk". Being explicit about where
coverage stops is the differentiator against a generic tool that scores everyone
regardless of whether the evidence supports it.
""",
}

st.set_page_config(page_title="AR Risk Demo", layout="wide")


def section_header(title: str, help_key: str) -> None:
    """Section heading with an ℹ️ popover explaining what it shows and,
    more importantly, which parts require manual operator work."""
    left, right = st.columns([0.88, 0.12], vertical_alignment="bottom")
    with left:
        st.subheader(title)
    with right:
        with st.popover("ℹ️", help="What this section shows, and what you must do manually"):
            st.markdown(MANUAL_STEPS[help_key])


# --- password gate ---------------------------------------------------------

def _expected_password() -> str | None:
    try:
        if "DEMO_PASSWORD" in st.secrets:
            return st.secrets["DEMO_PASSWORD"]
    except Exception:
        pass
    return os.environ.get("DEMO_PASSWORD")


def require_password() -> None:
    if st.session_state.get("authenticated"):
        return

    expected = _expected_password()
    if not expected:
        st.error(
            "No DEMO_PASSWORD configured. Set it in .streamlit/secrets.toml "
            "(DEMO_PASSWORD = \"...\") or as an environment variable before running this app."
        )
        st.stop()

    st.title("Accounts Receivable Risk — Demo Access")
    st.caption("Password-protected. Ask whoever set up this demo for access.")
    with st.form("login_form"):
        pwd = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Enter")
    if submitted:
        if pwd == expected:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    st.stop()


require_password()


# --- sidebar: methodology note, always visible, never behind a click -------

with st.sidebar:
    st.header("Methodology & Evidence Strength")
    st.caption("Identical text to the generated PDF/HTML reports — unedited.")
    st.markdown(METHODOLOGY_TEXT)

    st.divider()
    st.header("Operator checklist")
    st.caption("The manual work behind a real engagement, in order.")
    st.markdown(
        """
*This app is the demo only. Real engagements run via `run_pipeline.py` at the*
*project root, entirely on your machine — never uploaded here or anywhere else.*

**1. Get the ledger.** Client exports AR invoices (open + settled) from their
accounting system as CSV/Excel. Messy headers are fine.

**2. Copy the real templates for this engagement.** From `templates/` at the
project root: `external_signals_template.csv` and, if needed,
`customer_name_map_template.csv`. Copy them somewhere per-client — don't edit
the templates in place.

**3. Run it, then read the quarantine list.** Fix unparseable rows at source
and re-run rather than accepting a silent shortfall.

**4. Resolve customer-name variants.** Add `raw_name,canonical_name` rows to
your copy of the name-map template. Manual on purpose — auto-merging risks
combining two genuinely different companies.

**5. Research each customer — the real work.** For every customer, check
rating agencies (CRISIL / ICRA / CARE / India Ratings), IBBI + NCLT, MCA
(ADT-3, last AGM), and CDSCO/FDA. Record findings **with dates** in your copy
of the signals template.

**6. Classify each rating withdrawal.** Benign (debt repaid) vs.
non-cooperation (agency gave up). Read the actual withdrawal notice — this
one distinction drives most avoidable false positives.

**7. Set coverage honestly.** `has_public_rating` = `yes` / `no` / blank for
not-yet-researched. Don't let "unresearched" read as "safe".

**8. Generate and review the report before sending.** `python run_pipeline.py
--ledger ... --signals ...` — see `run_pipeline.py --help`. You're charging
for this; the evidence sentence is the deliverable, not the score.
"""
    )


# --- main area ---------------------------------------------------------------

st.title("Accounts Receivable Risk — Sales Demo")
st.caption(
    "Demo wrapper for live sales calls only. Real client engagements run from the "
    "local script-based pipeline, not this app."
)

CASE_STUDY_VIEW = "Illustrative Case Study (Orchid Pharma, 2017)"
LIVE_VIEW = "Try It Live"

# st.radio, not st.tabs: st.tabs mounts BOTH panels' content into the DOM
# up front and only toggles CSS visibility between them. That's fine for
# plain text, but the canvas-based st.dataframe grid below measures its
# container once at mount time - when mounted inside a hidden tab panel,
# it latches onto a ~52px width and never recovers, even after the tab
# becomes visible. st.radio only ever renders the selected branch's
# widgets at all, so the grid mounts already-visible and sizes correctly.
# It also preserves the selection across reruns (e.g. a file upload)
# more reliably than st.tabs did in testing, which kept snapping back to
# the first tab - disorienting mid-demo.
view = st.radio("View", [CASE_STUDY_VIEW, LIVE_VIEW], horizontal=True, label_visibility="collapsed")


# --- view 1: the already-built Orchid Pharma case study, embedded verbatim -

if view == CASE_STUDY_VIEW:
    section_header("Illustrative Case Study Report", "case_study")
    st.caption(
        "This is the same HTML the Stage 4 report generator produces — rendered inline "
        "so it reads live on a call instead of making the prospect wait on a file download."
    )

    @st.cache_data(show_spinner="Building case study report...")
    def _build_case_study_html() -> str:
        ledger_path = generate_case_study_ledger()
        result = parse_ledger_file(ledger_path)
        ledger_customers = sorted(result.clean_df["customer_name"].unique())
        monthly = compute_monthly_metrics(result.clean_df)
        trend = compute_rolling_trend(monthly)
        exposure = compute_exposure(result.clean_df)
        signals_df, _ = load_from_csv(CASE_STUDY_SIGNALS_PATH)
        coverage = build_coverage_screen(ledger_customers, signals_df)
        scores = score_all_customers(ledger_customers, coverage, signals_df, trend)
        context = build_report_context(
            scores,
            exposure,
            report_title="Accounts Receivable Risk Report — Illustrative Case Study",
            subtitle=(
                "Orchid Pharma Limited (2017) vs. Neuland Laboratories — built from a "
                "real, sourced historical signal"
            ),
            disclaimer_banner=CASE_STUDY_DISCLAIMER,
        )
        return render_html(context)

    st.iframe(_build_case_study_html(), height=1500)


# --- view 2: upload a sample ledger, run the pipeline live -----------------

else:
    section_header("Upload a sample ledger", "upload")
    st.warning(
        "Use clearly synthetic/sample data only during an actual demo call, never a "
        "prospect's real ledger — this uploader will technically accept anything; "
        "that discipline is on the operator, not enforced by the code."
    )
    uploaded = st.file_uploader("AR ledger (CSV or Excel)", type=["csv", "xlsx", "xls"])

    if uploaded is not None:
        with tempfile.NamedTemporaryFile(suffix=Path(uploaded.name).suffix, delete=False) as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = Path(tmp.name)

        try:
            result = parse_ledger_file(tmp_path)
        except ValueError as e:
            st.error(f"Could not read this file: {e}")
            st.stop()
        finally:
            tmp_path.unlink(missing_ok=True)

        section_header("Parsing", "parsing")
        c1, c2, c3 = st.columns(3)
        c1.metric("Rows read", result.total_rows)
        c2.metric("Parsed cleanly", result.parsed_rows)
        c3.metric("Quarantined", result.error_row_count)
        if result.error_row_count:
            with st.expander(f"{result.error_row_count} row(s) could not be parsed — reasons"):
                st.dataframe(
                    result.errors_df[["source_row_number", "reasons"]],
                    width="stretch",
                    hide_index=True,
                )

        if result.clean_df.empty:
            st.warning("No usable rows found in this file — nothing to score.")
            st.stop()

        # apply the bundled demo name-map before computing anything, same
        # as every local script does - this was previously missing here,
        # which meant the "Parsing" help text told you to edit
        # customer_name_map.csv while the app silently ignored it.
        name_map = load_name_map(NAME_MAP_PATH)
        clean_df, name_map_report = apply_name_map(result.clean_df, name_map)
        if name_map_report["mapped"]:
            st.caption(f"Name map applied: merged {', '.join(name_map_report['mapped'])} into its canonical name.")

        ledger_customers = sorted(clean_df["customer_name"].unique())
        monthly = compute_monthly_metrics(clean_df)
        trend = compute_rolling_trend(monthly)
        exposure = compute_exposure(clean_df)
        signals_df, _ = load_from_csv(SIGNALS_PATH)
        coverage = build_coverage_screen(ledger_customers, signals_df)
        scores = score_all_customers(ledger_customers, coverage, signals_df, trend)
        context = build_report_context(
            scores,
            exposure,
            report_title="Live Upload Result",
            subtitle=f"{uploaded.name} — scored against the bundled sample external-signals data",
        )

        st.info(
            "Customers in this file are matched against the bundled sample external-signals "
            "data. Anyone not in that file correctly shows as 'not yet researched' below — "
            "that's the coverage screen working as designed, not a bug."
        )

        section_header("Executive Summary", "summary")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total customers", context["total_customers"])
        m2.metric("Rated", context["rated_count"])
        m3.metric("Unrated", context["unrated_count"])
        m4.metric("Not yet researched", context["not_researched_count"])
        st.write(
            f"**Total exposure:** {context['total_exposure']}  |  "
            f"**Rated group:** {context['rated_exposure']}  |  "
            f"**Out of coverage:** {context['out_of_coverage_exposure']}"
        )
        if context["has_negative_exposure"]:
            st.caption(context["negative_exposure_note"])

        section_header("Ranked Risk List — Rated / In-Coverage Customers", "ranked")
        st.caption(
            "Only customers with a confirmed public rating history are ranked here — "
            "ranking anyone else would imply evidence that doesn't exist for them."
        )
        if context["ranked_customers"]:
            st.dataframe(pd.DataFrame(context["ranked_customers"]), width="stretch", hide_index=True)
        else:
            st.write("No rated customers with a nonzero score in this file.")

        if context["reviewed_not_flagged"]:
            section_header("Reviewed, Not Flagged", "reviewed")
            st.caption("Signals this tool checked for and deliberately chose not to score as risk.")
            for r in context["reviewed_not_flagged"]:
                st.success(f"**{r['customer_name']}**: {r['note']}")

        section_header("Unrated / Not-Yet-Researched Customers", "uncovered")
        st.caption(
            "NOT scored or ranked. A customer here with no flags is not confirmed "
            "low-risk — this tool's strongest evidence simply doesn't apply to them."
        )
        if context["unrated_customers"]:
            st.dataframe(pd.DataFrame(context["unrated_customers"]), width="stretch", hide_index=True)
        else:
            st.write("Every customer in this file is within the rated/in-coverage group.")
    else:
        st.caption("No file uploaded yet.")
