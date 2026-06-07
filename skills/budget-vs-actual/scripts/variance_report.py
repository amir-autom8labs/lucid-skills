#!/usr/bin/env python3
"""Build a ranked budget-vs-actual variance report from a Lucid ``get_bva`` payload.

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

# Import the shared helper from the plugin's scripts dir. ``CLAUDE_PLUGIN_ROOT``
# is set when the skill runs inside the plugin; fall back to this file's location
# (skills/<skill>/scripts/ -> ../../../scripts).
_PLUGIN_ROOT = os.environ.get(
    "CLAUDE_PLUGIN_ROOT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")),
)
sys.path.insert(0, os.path.join(_PLUGIN_ROOT, "scripts"))

from lucid_utils import (  # noqa: E402
    fmt,
    load_json,
    to_decimal,
    tieout_status,
    variance_table,
)

# P&L/BVA row numbers whose increase is an *expense* (more actual than budget is
# bad). Everything else on the income statement (revenue, gross margin, the
# income/profit subtotals) reads the other way: more is good. Subtotal expense
# lines (13 Total OpEx, 27 Total expenses) and the detail expense lines (10 R&D,
# 11 S&M, 12 G&A, 6 COGS, 17 Financial, 18 Other, 21 Taxes, 29 Depreciation) are
# expenses; note-detail expense rows live at row_num >= 33.
_EXPENSE_SUMMARY_ROWS = {6, 10, 11, 12, 13, 17, 18, 21, 27, 29}
# Note sections that are pure expense detail (see report-reference P&L note map):
#   Note 2 COGS 58-84, Note 3 R&D 86-106, Note 4 S&M 109-137, Note 5 G&A 140-175,
#   Note 6 Financial 178-191, Note 7 Other 194-198, Note 8 Taxes 201-208.
_EXPENSE_NOTE_RANGE = range(58, 209)
# Revenue note detail (Note 1, rows 35-53) is revenue, not expense.
_REVENUE_NOTE_RANGE = range(35, 54)


def _is_expense_row(row_num: int | None) -> bool:
    """Does an *increase* in this row's actual hurt the bottom line?

    True for cost/expense lines (over-budget = unfavorable). False for revenue and
    for the profit subtotals (under-budget = unfavorable). Defaults to revenue-like
    treatment for unknown rows, which is the safe reading for top-of-statement lines.
    """
    if row_num is None:
        return False
    if row_num in _EXPENSE_SUMMARY_ROWS:
        return True
    if row_num in _REVENUE_NOTE_RANGE:
        return False
    if row_num in _EXPENSE_NOTE_RANGE:
        return True
    return False


def classify(row_num: int | None, variance: Decimal) -> str:
    """FAVORABLE / UNFAVORABLE / NEUTRAL for a variance, by section then sign.

    * Expense row: positive variance (spent more than planned) is UNFAVORABLE.
    * Revenue / profit row: positive variance (beat the plan) is FAVORABLE.
    * Exactly on plan: NEUTRAL.
    """
    if variance == 0:
        return "NEUTRAL"
    over = variance > 0
    if _is_expense_row(row_num):
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
        tag = "" if var is None else f"  [{classify(None if not expense else 6, var)}]"
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
    # Drop subtotals that merely echo a detail line we already show? Keep them:
    # subtotals are the headline drivers and are what a reader scans first.
    fav: list[dict] = []
    unfav: list[dict] = []
    for r in table[:top]:
        verdict = classify(r["row"], r["variance"])
        r["_verdict"] = verdict
        r["_material"] = _is_material(r["variance"], threshold)
        if verdict == "FAVORABLE":
            fav.append(r)
        elif verdict == "UNFAVORABLE":
            unfav.append(r)

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
