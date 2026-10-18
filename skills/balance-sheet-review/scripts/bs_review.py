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

# Self-contained: this skill bundles lucid_utils.py beside this script. Prepend
# this script's own dir so `from lucid_utils import ...` resolves to the sibling
# copy in any runtime (Claude Code, Managed Agents, claude.ai) — the whole skill
# dir, scripts included, is uploaded together, so no absolute plugin path is needed.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lucid_utils import (  # noqa: E402
    Figure,
    bs_cash,
    bs_cash_disclosures,
    fmt,
    fmt_cash_reconciliation,
    fmt_figure,
    load_json,
    role_figure,
    tieout_status,
    total_figure,
)

# Why there are no row numbers in this file any more
# --------------------------------------------------
# It used to open with sixteen pinned Balance-Sheet rows — ``ROW_CASH = 5``,
# ``ROW_AR = 8``, ... — plus eight more for intercompany. Every one of them was
# read off the one reference chart the canonical skeleton was traced from, and every one of them was correct there and nowhere else: a
# generated chart's BS rows come out in the order that tenant's routing
# produced them, so row 5 is whichever asset the routing happened to put first.
# On a company whose current assets sort debtors-before-bank, this file stated
# trade debtors as cash and computed a quick ratio from it — silently, because
# prose output has no footing check to catch it.
#
# What replaces them splits in two, and the split is the honest finding of this
# ticket rather than an implementation detail:
#
# * The **structural** rows — the totals and the scaffold — carry a stable
#   ``role`` on the wire (or appear in the ``totals`` block, which is better
#   still: computed once in the backend and rendered here verbatim). Those are
#   resolved below and are fully position-free.
#
# * The **account-level leaves** — cash, AR, other receivable, AP, deferred
#   income, SAFE, share capital, APIC, retained earnings, and the intercompany
#   rows — have no identity on the wire at all. A BS detail row's label IS the
#   routed ``main_class`` verbatim, so it is addressable, but only in the
#   TENANT'S OWN vocabulary: nothing anywhere says which of a company's mains
#   MEANS "accounts receivable". ``is_cash_pool`` works for cash precisely
#   because it is a semantic flag someone sets in Settings; there is no
#   equivalent for the rest.
#
# So this review now DECLINES those lines instead of reading them positionally.
# Matching a label like "Accounts receivable" would be the same class of bug as
# the pins — it would simply fail on a tenant who calls it "Trade debtors"
# rather than on one whose rows shifted. Trading a silent failure for a
# differently-silent failure is not a fix.

# The shared reason every declined leaf reports. One string, because they all
# fail for exactly one reason and a reader should recognise it as systemic
# rather than as nine unrelated gaps.
_NO_SEMANTIC_IDENTITY = (
    "the wire carries no semantic identity for this line — a BS leaf is named "
    "only by the tenant's own main_class vocabulary"
)


def _declined(line: str) -> Figure:
    """A leaf this review cannot identify — reported as such, never as 0."""
    return Figure(unresolved_reason=f"{line}: {_NO_SEMANTIC_IDENTITY}")


def _abs(value: Decimal | None) -> Decimal | None:
    return None if value is None else abs(value)


def _abs_figure(figure: Figure) -> Figure:
    """Magnitude of a figure, carrying an unresolved state through unchanged.

    Taking ``abs()`` of "I don't know" must not produce a number — the reason
    rides along so the caller still renders "not identified".
    """
    return Figure(value=_abs(figure.value), unresolved_reason=figure.unresolved_reason)


def _negate_figure(figure: Figure) -> Figure:
    """Sign-flip a figure (wire → human), carrying an unresolved state through."""
    return Figure(
        value=None if figure.value is None else -figure.value,
        unresolved_reason=figure.unresolved_reason,
    )


def _prefer_total(report: dict, total_key: str, role: str) -> Figure:
    """A headline figure from ``totals`` if present, else from the row's ``role``."""
    figure = total_figure(report, total_key)
    return figure if figure.resolved else role_figure(report, role)


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


# ``quick_ratio()`` was deleted with its last caller. The acid test needs the
# cash and accounts-receivable LEAVES; cash now resolves via ``totals.cash`` but
# AR has no identity on the wire, so the ratio is refused rather than computed
# (see ``main``). A helper kept "for when AR resolves" would be dead code that
# reads as a working feature, and ruff does not flag an unused module-level
# function.


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: bs_review.py <balance_sheet.json | ->", file=sys.stderr)
        return 2
    bs = load_json(argv[0])

    # --- Structural rows: resolved by identity (signed, as on the wire) ---- #
    # ``totals`` first where it carries the figure — computed once in the
    # backend, rendered here verbatim — with the row's stable ``role`` as the
    # fallback for a payload whose totals block was projected away.
    tca = role_figure(bs, "total_current_assets")
    tcl = role_figure(bs, "total_current_liabilities")
    total_ltl = role_figure(bs, "total_long_term_liabilities")

    t_assets = _prefer_total(bs, "total_assets", "total_assets")
    t_liabilities = _prefer_total(bs, "total_liabilities", "total_liabilities")
    t_equity = _prefer_total(bs, "total_equity", "total_equity")
    cy_pl = role_figure(bs, "pl_loss_profit")

    # --- Account-level leaves: no identity on the wire, so declined -------- #
    # Cash IS resolvable — the backend publishes it in ``totals.cash``: the
    # balance of the is_cash_pool accounts, wherever the statement presents
    # them. Every other leaf below still has no identity on the wire.
    cash = bs_cash(bs)
    ar = _declined("Accounts receivable")
    other_recv = _declined("Other receivable")
    ap = _declined("Accounts payable")
    deferred = _declined("Deferred income")
    safe = _declined("SAFE")

    # --- Derived liquidity metrics (sign-aware) ---------------------------- #
    wc = (
        Figure(value=working_capital(tca.value, tcl.value))
        if (tca.resolved and tcl.resolved)
        else Figure(unresolved_reason="working capital needs both TCA and TCL")
    )
    cr = current_ratio(tca.value, tcl.value) if (tca.resolved and tcl.resolved) else None
    # The quick ratio needs cash AND accounts receivable. Cash now resolves;
    # AR still has no identity on the wire, so the ratio is NOT computed and
    # NOT shown as "—". An acid test built from a guessed receivables line is a
    # liquidity verdict on the wrong lines, and this ratio is one a reader acts
    # on.
    qr_declined = (
        "accounts receivable: " + _NO_SEMANTIC_IDENTITY + " (cash resolves; AR does not)"
    )

    tie = tieout_status(bs)

    label = bs.get("period", {}).get("label", "?")
    view = bs.get("view", "?")

    # --- Present: ASSETS positive, LIABILITIES/EQUITY sign-flipped --------- #
    print(f"BALANCE SHEET REVIEW — {label} (view: {view})")
    print("=" * 60)

    print("\nASSETS (magnitudes)")
    print(f"  {'Cash & equivalents':<32} {fmt_figure(cash):>16}")
    # Beside the figure: the amount of cash presented outside a cash class,
    # then every backend clause — "includes" (that cash) and "excludes" (a
    # cash class's accounts that are not cash, which carries no amount).
    for line in fmt_cash_reconciliation(bs):
        print(f"    ↳ {line}")
    for disclosure in bs_cash_disclosures(bs):
        print(f"    ↳ NOTE: {disclosure}")
    print(f"  {'Accounts receivable':<32} {fmt_figure(ar):>16}")
    print(f"  {'Other receivable':<32} {fmt_figure(other_recv):>16}")
    print(f"  {'Total current assets':<32} {fmt_figure(tca):>16}")
    print(f"  {'TOTAL ASSETS':<32} {fmt_figure(t_assets):>16}")

    print("\nLIABILITIES (magnitudes — sign flipped)")
    print(f"  {'Accounts payable':<32} {fmt_figure(_abs_figure(ap)):>16}")
    print(f"  {'Deferred income':<32} {fmt_figure(_abs_figure(deferred)):>16}")
    print(f"  {'Total current liabilities':<32} {fmt_figure(_abs_figure(tcl)):>16}")
    print(f"  {'SAFE':<32} {fmt_figure(_abs_figure(safe)):>16}")
    print(f"  {'Total long-term liabilities':<32} {fmt_figure(_abs_figure(total_ltl)):>16}")
    print(f"  {'TOTAL LIABILITIES':<32} {fmt_figure(_abs_figure(t_liabilities)):>16}")

    # Equity sign convention & the negative-book-equity flag.
    # On the wire, positive book equity is stored NEGATIVE; flip it for humans:
    #   displayed_equity = -t_equity   (so wire -4.27M -> +4.27M of book equity)
    # Accumulated losses can push real book equity below zero. The reliable
    # driver to inspect is retained earnings + current-year P&L (rows 56 + 55):
    # if those net to a loss large enough, book equity is negative even when the
    # headline total nets positive (e.g. SAFE parked in long-term liabilities).
    displayed_equity = _negate_figure(t_equity)

    print("\nEQUITY (magnitudes — sign flipped)")
    # Share capital + APIC and the accumulated position are both DECLINED, and
    # the accumulated one is worth spelling out: current-year P&L resolves
    # cleanly (role ``pl_loss_profit``) but retained earnings does not, and
    # ``retained + cy_pl`` computed from only the half that resolved is short
    # by the whole opening position while still looking like a total. A partial
    # sum presented as "accumulated earnings" is a wrong number, not a partial
    # one.
    share_capital_apic = _declined("Share capital + APIC")
    accumulated = _declined("Accumulated earnings/(losses)")
    print(f"  {'Share capital + APIC':<32} {fmt_figure(share_capital_apic):>16}")
    print(f"  {'Accumulated earnings/(losses)':<32} {fmt_figure(accumulated):>16}")
    print(f"  {'  of which current-year P&L':<32} "
          f"{fmt_figure(_negate_figure(cy_pl)):>16}")
    eq_note = ""
    if displayed_equity.value is not None and displayed_equity.value < 0:
        eq_note = "  ⚠ NEGATIVE book equity"
    print(f"  {'Total equity (book)':<32} {fmt_figure(displayed_equity):>16}{eq_note}")

    print("\nLIQUIDITY")
    print(f"  {'Working capital (TCA + TCL)':<32} {fmt_figure(wc):>16}")
    print(f"  {'Current ratio (TCA / |TCL|)':<32} "
          f"{('—' if cr is None else f'{cr:.2f}x'):>16}")
    print(f"  {'Quick ratio ((cash+AR)/|TCL|)':<32} {'not computed':>16}")
    print(f"    ↳ {qr_declined}")

    print("\nINTERCOMPANY")
    # Deliberately a refusal rather than a number. The intercompany rows were
    # eight pinned positions netted across entities for a GROUP view, and
    # consolidation is the one place a reader has no independent sense of what
    # the figure should be — a wrong number here is undetectable by the person
    # most likely to catch it anywhere else. Declining is the safe failure;
    # netting eight guessed rows is not.
    print(f"  {'Net intercompany':<32} {'not computed':>16}")
    print(f"    ↳ {_NO_SEMANTIC_IDENTITY}")

    print("\nTIE-OUT")
    flag = {True: "OK", False: "OFF", None: "n/a"}[tie["ok"]]
    print(f"  balance_check_delta = {fmt(tie['delta'])}  [{flag}]")
    if tie["ok"] is False:
        print("  ⚠ Books do NOT tie out — treat figures as suspect.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
