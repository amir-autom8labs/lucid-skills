#!/usr/bin/env python3
"""Build a ranked budget-vs-actual variance report from a Lucid ``get_bva`` payload.

NOTE: ``get_bva`` is temporarily soft-disabled and returns a "budget-vs-actual is
not available yet" stub, so this script has no real payload to rank right now.
It is kept intact for when the tool is re-enabled; until then, relay that
budget-vs-actual isn't available yet instead of running it on a stub.

Reads a (possibly spilled-to-file) BVA report and prints:

* the headline actual / budget / variance for revenue, OpEx, and net profit,
* the top-N variances by absolute size, each tagged **FAVORABLE** / **UNFAVORABLE**
  using the correct interpretation for its section (over-spending an expense is
  unfavorable; under-performing on revenue is unfavorable),
* the tie-out check so you never present numbers off un-reconciled books.

The favorable/unfavorable call is the whole point: ``variance = actual - budget``
has the *same* arithmetic sign for revenue and expense rows, but the *business*
meaning flips. This script resolves that by the line's P&L role, not by the raw
sign — see ``_is_expense_row``.

Usage::

    python variance_report.py <bva.json> --top 10

Stdlib only, plus the shared ``lucid_utils`` helper (so money is parsed the same
way everywhere). Pass ``-`` to read the payload from stdin.
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal

# Self-contained: this skill bundles lucid_utils.py beside this script. Prepend
# this script's own dir so `from lucid_utils import ...` resolves to the sibling
# copy in any runtime (Claude Code, Managed Agents, claude.ai) — the whole skill
# dir, scripts included, is uploaded together, so no absolute plugin path is needed.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lucid_utils import (  # noqa: E402
    expense_polarity,
    fmt,
    load_json,
    to_decimal,
    tieout_status,
    variance_table,
)

# Which side of the bottom line a row sits on is resolved by IDENTITY, via
# ``lucid_utils.expense_polarity`` — never by its row number.
#
# This block used to be ten pinned P&L rows plus two pinned note RANGES
# (``_EXPENSE_SUMMARY_ROWS = {6, 10, 11, ...}``, ``range(58, 209)``,
# ``range(35, 54)``). They were the most dangerous pins in the plugin and they
# outlived the sweep that removed every other one, because a leading underscore
# and a SET literal slipped past the scan.
#
# Dangerous because they do not merely report a wrong FIGURE — they decide a
# VERDICT. On a tenant with five operating-expense functions every row below the
# band shifts by two, so real expense rows fall out of the summary set and get
# revenue treatment while revenue note rows slide into the expense range: two
# lines swap sides at once and the report still looks well-formed. "Spent $80k
# more than plan" then prints as FAVORABLE.
#
# The ranges were worse than the scalars. A pinned range claims a whole SPAN of
# a layout that shifts, so it silently gains and loses members together.

# The verdict for a row whose side could not be resolved. NOT a default guess:
# inverting a variance is worse than declining to judge it, because a wrong
# verdict is read as a finding while a declined one is read as a question.
UNKNOWN = "UNKNOWN"


def classify(is_expense: bool | None, variance: Decimal) -> str:
    """FAVORABLE / UNFAVORABLE / NEUTRAL for a variance, by side then sign.

    * Expense row: positive variance (spent more than planned) is UNFAVORABLE.
    * Revenue / profit row: positive variance (beat the plan) is FAVORABLE.
    * Exactly on plan: NEUTRAL.
    * Side unresolved (``is_expense is None``): ``UNKNOWN`` — say so, never guess.
    """
    if variance == 0:
        return "NEUTRAL"
    if is_expense is None:
        return UNKNOWN
    over = variance > 0
    if is_expense:
        return "UNFAVORABLE" if over else "FAVORABLE"
    return "FAVORABLE" if over else "UNFAVORABLE"


def _pct_str(variance_pct: float | int | None) -> str:
    """Render ``variance_pct`` (a float fraction, or None when budget == 0)."""
    if variance_pct is None:
        return "n/a"  # no budget mapping → percentage is undefined, not zero
    return f"{float(variance_pct) * 100:+.1f}%"


def _is_material(variance: Decimal, threshold: Decimal) -> bool:
    return abs(variance) >= threshold


def headline(bva: dict) -> None:
    """Print the three figures a CFO reads first: revenue, OpEx, net profit."""
    totals = bva.get("totals", {})

    def line(label: str, prefix: str, expense: bool) -> None:
        actual = to_decimal(totals.get(f"{prefix}_actual"))
        budget = to_decimal(totals.get(f"{prefix}_budget"))
        var = to_decimal(totals.get(f"{prefix}_variance"))
        tag = "" if var is None else f"  [{classify(expense, var)}]"
        print(
            f"  {label:<16} actual {fmt(actual):>14}   "
            f"budget {fmt(budget):>14}   var {fmt(var):>14}{tag}"
        )

    print("HEADLINE  (actual vs plan)")
    line("Revenue", "revenues", expense=False)
    line("Total OpEx", "total_expenses", expense=True)
    line("Operating inc.", "operating_income", expense=False)
    line("Net profit", "net_profit", expense=False)


def ranked(bva: dict, top: int, threshold: Decimal) -> None:
    """Print the top-N variances by |variance|, split favorable / unfavorable."""
    table = variance_table(bva)  # already ranked by |variance|, all rows
    # row_num -> is-expense, resolved by identity. A row ABSENT from this map
    # gets no verdict rather than a guessed one.
    polarity = expense_polarity(bva)
    # Drop subtotals that merely echo a detail line we already show? Keep them:
    # subtotals are the headline drivers and are what a reader scans first.
    fav: list[dict] = []
    unfav: list[dict] = []
    unknown: list[dict] = []
    for r in table[:top]:
        verdict = classify(polarity.get(r["row"]), r["variance"])
        r["_verdict"] = verdict
        r["_material"] = _is_material(r["variance"], threshold)
        if verdict == "FAVORABLE":
            fav.append(r)
        elif verdict == "UNFAVORABLE":
            unfav.append(r)
        elif verdict == UNKNOWN:
            # Listed, never dropped. A material variance silently missing from
            # both blocks is indistinguishable from one that did not occur —
            # the reader would conclude the line was fine.
            unknown.append(r)

    def block(title: str, rows: list[dict]) -> None:
        print(f"\n{title}")
        if not rows:
            print("  (none in top variances)")
            return
        for r in rows:
            flag = " *" if r["_material"] else "  "
            big_pct = (
                r["variance_pct"] is not None and abs(float(r["variance_pct"])) >= 0.25
            )
            note = "  <-- large % on material base" if (big_pct and r["_material"]) else ""
            print(
                f" {flag}[{r['row']:>4}] {r['label']:<40} "
                f"var {fmt(r['variance']):>13} ({_pct_str(r['variance_pct'])})"
                f"{note}"
            )

    block("UNFAVORABLE (worst misses first)", unfav)
    block("FAVORABLE (best beats first)", fav)
    if unknown:
        block("SIDE NOT IDENTIFIED (no verdict — do NOT call these good or bad)", unknown)
        print(
            "    ^ these rows carry no band_key / heading_key / role this script "
            "recognises,\n      so whether over-budget is good or bad is unknown. "
            "Report the variance and\n      say the direction could not be "
            "determined; never guess a side."
        )
    print("\n  * = material (|variance| >= threshold); n/a % = no budget mapping")


def tie_out(bva: dict) -> None:
    status = tieout_status(bva)
    flag = {True: "OK", False: "OFF", None: "n/a"}[status["ok"]]
    print(f"\nTIE-OUT: {flag}  (check_delta {fmt(status['delta'])})")
    if status["ok"] is False:
        print("  WARNING: books do not reconcile — treat variances as suspect.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", help="get_bva payload (path, or - for stdin)")
    parser.add_argument("--top", type=int, default=10, help="rank top N by |variance|")
    parser.add_argument(
        "--material",
        type=Decimal,
        default=Decimal("10000"),
        help="materiality threshold in dollars for the * flag (default 10000)",
    )
    args = parser.parse_args(argv)

    bva = load_json(args.file)
    label = bva.get("period", {}).get("label", "?")
    print(f"=== Budget vs Actual — {label} ===\n")
    headline(bva)
    ranked(bva, args.top, args.material)
    tie_out(bva)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
