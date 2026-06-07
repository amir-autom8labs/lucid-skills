#!/usr/bin/env python3
"""Balance-sheet liquidity & financial-position review from a get_balance_sheet payload.

The balance sheet is a **snapshot** (position as of period end). Lucid's sign
convention is the trap this script exists to handle safely:

* asset balances are **positive**,
* liability and equity balances are **negative**,
* and the three sum to ~0 (``total_assets + total_liabilities + total_equity == 0``).

So for a human you must **flip the sign** of liabilities/equity to show positive
magnitudes, and the working-capital / ratio math has to be explicit about signs.
This script does all of that in one place so no skill gets it wrong by hand.

Usage::

    python bs_review.py <balance_sheet.json>

Accepts a tool result that was spilled to a file (pass the path) or ``-`` for
stdin. Stdlib only, plus the shared ``lucid_utils`` for money parsing.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal

# Import the shared helper. ${CLAUDE_PLUGIN_ROOT}/scripts is the canonical home;
# fall back to the repo layout (two dirs up from this script) when running locally.
_PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT")
_CANDIDATES = [
    os.path.join(_PLUGIN_ROOT, "scripts") if _PLUGIN_ROOT else None,
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts"),
]
for _c in _CANDIDATES:
    if _c and os.path.isdir(_c):
        sys.path.insert(0, _c)
        break

# Self-contained: this skill bundles lucid_utils.py beside this script. Prepend
# this script's own dir so the import resolves in any runtime (incl. claude.ai),
# whether or not CLAUDE_PLUGIN_ROOT is set.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lucid_utils import fmt, find_row, load_json, tieout_status, to_decimal  # noqa: E402

# Stable balance-sheet template rows (see reference/report-reference.md).
ROW_CASH = 5
ROW_AR = 8
ROW_OTHER_RECEIVABLE = 11
ROW_TOTAL_CURRENT_ASSETS = 16
ROW_TOTAL_ASSETS = 24
ROW_AP = 29
ROW_DEFERRED_INCOME = 32
ROW_TOTAL_CURRENT_LIABILITIES = 35
ROW_SAFE = 39
ROW_TOTAL_LONG_TERM_LIABILITIES = 44
ROW_SHARE_CAPITAL = 46
ROW_APIC = 51
ROW_CURRENT_YEAR_PL = 55
ROW_RETAINED_EARNINGS = 56
ROW_TOTAL_EQUITY = 57
ROW_TOTAL_LIAB_AND_EQUITY = 59

# Intercompany rows — net these across entities for a group view.
ROWS_INTERCOMPANY = [12, 13, 14, 21, 40, 41, 42, 43]


def _abs(value: Decimal | None) -> Decimal | None:
    return None if value is None else abs(value)


def working_capital(
    current_assets: Decimal | None, current_liabilities: Decimal | None
) -> Decimal | None:
    """Working capital = current assets + current liabilities.

    Current liabilities arrive **negative** in Lucid's convention, so a plain
    *addition* already nets correctly (assets minus the magnitude of liabilities).
    Do NOT subtract — that would double-count the sign.
    """
    if current_assets is None or current_liabilities is None:
        return None
    return current_assets + current_liabilities


def current_ratio(
    current_assets: Decimal | None, current_liabilities: Decimal | None
) -> Decimal | None:
    """current assets ÷ |current liabilities| — take the magnitude of liabilities."""
    denom = _abs(current_liabilities)
    if current_assets is None or denom is None or denom == 0:
        return None
    return current_assets / denom


def quick_ratio(
    cash: Decimal | None, ar: Decimal | None, current_liabilities: Decimal | None
) -> Decimal | None:
    """(cash + AR) ÷ |current liabilities| — the acid test, excludes slower assets."""
    denom = _abs(current_liabilities)
    if cash is None or ar is None or denom is None or denom == 0:
        return None
    return (cash + ar) / denom


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: bs_review.py <balance_sheet.json | ->", file=sys.stderr)
        return 2
    bs = load_json(argv[0])

    # --- Pull the headline template rows (signed, as on the wire) ----------- #
    cash = find_row(bs, ROW_CASH)
    ar = find_row(bs, ROW_AR)
    other_recv = find_row(bs, ROW_OTHER_RECEIVABLE)
    tca = find_row(bs, ROW_TOTAL_CURRENT_ASSETS)
    total_assets = find_row(bs, ROW_TOTAL_ASSETS)
    ap = find_row(bs, ROW_AP)
    deferred = find_row(bs, ROW_DEFERRED_INCOME)
    tcl = find_row(bs, ROW_TOTAL_CURRENT_LIABILITIES)
    safe = find_row(bs, ROW_SAFE)
    total_ltl = find_row(bs, ROW_TOTAL_LONG_TERM_LIABILITIES)
    total_equity = find_row(bs, ROW_TOTAL_EQUITY)

    totals = bs.get("totals", {})
    t_assets = to_decimal(totals.get("total_assets")) or total_assets
    t_liabilities = to_decimal(totals.get("total_liabilities"))
    t_equity = to_decimal(totals.get("total_equity")) or total_equity

    # --- Derived liquidity metrics (sign-aware) ---------------------------- #
    wc = working_capital(tca, tcl)
    cr = current_ratio(tca, tcl)
    qr = quick_ratio(cash, ar, tcl)

    # --- Intercompany net (across entities) -------------------------------- #
    ic_total = Decimal(0)
    ic_found = False
    for rn in ROWS_INTERCOMPANY:
        v = find_row(bs, rn)
        if v is not None:
            ic_total += v
            ic_found = True

    tie = tieout_status(bs)

    label = bs.get("period", {}).get("label", "?")
    view = bs.get("view", "?")

    # --- Present: ASSETS positive, LIABILITIES/EQUITY sign-flipped --------- #
    print(f"BALANCE SHEET REVIEW — {label} (view: {view})")
    print("=" * 60)

    print("\nASSETS (magnitudes)")
    print(f"  {'Cash & equivalents':<32} {fmt(cash):>16}")
    print(f"  {'Accounts receivable':<32} {fmt(ar):>16}")
    print(f"  {'Other receivable':<32} {fmt(other_recv):>16}")
    print(f"  {'Total current assets':<32} {fmt(tca):>16}")
    print(f"  {'TOTAL ASSETS':<32} {fmt(t_assets):>16}")

    print("\nLIABILITIES (magnitudes — sign flipped)")
    print(f"  {'Accounts payable':<32} {fmt(_abs(ap)):>16}")
    print(f"  {'Deferred income':<32} {fmt(_abs(deferred)):>16}")
    print(f"  {'Total current liabilities':<32} {fmt(_abs(tcl)):>16}")
    print(f"  {'SAFE':<32} {fmt(_abs(safe)):>16}")
    print(f"  {'Total long-term liabilities':<32} {fmt(_abs(total_ltl)):>16}")
    print(f"  {'TOTAL LIABILITIES':<32} {fmt(_abs(t_liabilities)):>16}")

    # Equity sign convention & the negative-book-equity flag.
    # On the wire, positive book equity is stored NEGATIVE; flip it for humans:
    #   displayed_equity = -t_equity   (so wire -4.27M -> +4.27M of book equity)
    # Accumulated losses can push real book equity below zero. The reliable
    # driver to inspect is retained earnings + current-year P&L (rows 56 + 55):
    # if those net to a loss large enough, book equity is negative even when the
    # headline total nets positive (e.g. SAFE parked in long-term liabilities).
    share_capital = find_row(bs, ROW_SHARE_CAPITAL)
    apic = find_row(bs, ROW_APIC)
    cy_pl = find_row(bs, ROW_CURRENT_YEAR_PL)
    retained = find_row(bs, ROW_RETAINED_EARNINGS)
    displayed_equity = None if t_equity is None else -t_equity

    # Accumulated position = retained earnings + current-year P&L, sign-flipped
    # to a human magnitude (negative magnitude here = accumulated LOSS).
    accumulated = None
    if cy_pl is not None or retained is not None:
        accumulated = -((cy_pl or Decimal(0)) + (retained or Decimal(0)))

    print("\nEQUITY (magnitudes — sign flipped)")
    if share_capital is not None:
        print(f"  {'Share capital + APIC':<32} "
              f"{fmt(-((share_capital or Decimal(0)) + (apic or Decimal(0)))):>16}")
    if accumulated is not None:
        print(f"  {'Accumulated earnings/(losses)':<32} {fmt(accumulated):>16}")
    eq_note = ""
    if displayed_equity is not None and displayed_equity < 0:
        eq_note = "  ⚠ NEGATIVE book equity"
    elif accumulated is not None and accumulated < 0:
        eq_note = "  ⚠ accumulated losses"
    print(f"  {'Total equity (book)':<32} {fmt(displayed_equity):>16}{eq_note}")

    print("\nLIQUIDITY")
    print(f"  {'Working capital (TCA + TCL)':<32} {fmt(wc):>16}")
    print(f"  {'Current ratio (TCA / |TCL|)':<32} "
          f"{('—' if cr is None else f'{cr:.2f}x'):>16}")
    print(f"  {'Quick ratio ((cash+AR)/|TCL|)':<32} "
          f"{('—' if qr is None else f'{qr:.2f}x'):>16}")

    if ic_found:
        print("\nINTERCOMPANY (net across entities; >0 = net receivable)")
        print(f"  {'Net intercompany':<32} {fmt(ic_total):>16}")

    print("\nTIE-OUT")
    flag = {True: "OK", False: "OFF", None: "n/a"}[tie["ok"]]
    print(f"  balance_check_delta = {fmt(tie['delta'])}  [{flag}]")
    if tie["ok"] is False:
        print("  ⚠ Books do NOT tie out — treat figures as suspect.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
