#!/usr/bin/env python3
"""Assemble a cross-statement financial-position snapshot from Lucid payloads.

This is the close / "how are we doing" workhorse. It takes the four reports a
position review leans on — dashboard, P&L, balance sheet, cash flow — and emits
ONE consolidated view: the headline figures plus, crucially, the **tie-out
status of every report in one place**. A position review is only as trustworthy
as its weakest reconciliation, so the script refuses to let any single off-by
hide inside a wall of numbers.

It does no parsing of its own — every figure goes through ``lucid_utils`` so a
margin here matches a margin in any other skill. Read money straight from the
envelope (never divide by 100); the dashboard's mixed units (bps→%, months) are
handled by ``kpi_view``.

Two ways to use it::

    # CLI — point at the four (possibly spilled-to-file) tool results:
    python position_review.py \\
        --dashboard dash.json --pl pl.json --bs bs.json --cf cf.json

    # any subset is fine; omit what you didn't pull:
    python position_review.py --dashboard dash.json --pl pl.json

Stdlib only; imports the shared helper. Run it after you've saved each tool
result to a file (or pass ``-`` to read one from stdin).
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

# Self-contained: this skill bundles lucid_utils.py beside this script. Prepend
# this script's own dir so `from lucid_utils import ...` resolves to the sibling
# copy in any runtime (Claude Code, Managed Agents, claude.ai) — the whole skill
# dir, scripts included, is uploaded together, so no absolute plugin path is needed.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lucid_utils import (  # noqa: E402
    Figure,
    fmt,
    fmt_figure,
    heading_figure,
    kpi_view,
    load_json,
    pct,
    role_figure,
    tieout_status,
    to_decimal,
    total_figure,
)


def _prefer_total(report: dict[str, Any], total_key: str, role: str) -> Figure:
    """A headline figure from ``totals`` if it is there, else from the row's ``role``.

    ``totals`` is the better source — computed once in the backend and rendered
    verbatim here — but it is projected away by a ``fields=[...]`` request, so
    the row's stable ``role`` is the fallback. Both are identities; neither is
    a position.
    """
    figure = total_figure(report, total_key)
    return figure if figure.resolved else role_figure(report, role)


def _tieout_line(name: str, report: dict[str, Any] | None) -> tuple[str, bool | None]:
    """Render one report's reconciliation as a printable line + its ok flag."""
    if report is None:
        return (f"  {name:<14} not pulled", None)
    st = tieout_status(report)
    flag = {True: "OK", False: "OFF", None: "n/a"}[st["ok"]]
    delta = fmt(st["delta"]) if st["delta"] is not None else "—"
    return (f"  {name:<14} {flag:<3}  (delta {delta}, {st['kind']})", st["ok"])


def review(
    dashboard: dict[str, Any] | None = None,
    pl: dict[str, Any] | None = None,
    bs: dict[str, Any] | None = None,
    cf: dict[str, Any] | None = None,
) -> int:
    """Print the consolidated snapshot. Returns 1 if any tie-out is OFF."""
    print("=== TIE-OUT (verify before trusting any figure) ===")
    flags: list[bool | None] = []
    for name, rep in (
        ("dashboard", dashboard),
        ("p&l", pl),
        ("balance sheet", bs),
        ("cash flow", cf),
    ):
        line, ok = _tieout_line(name, rep)
        print(line)
        flags.append(ok)
    any_off = any(f is False for f in flags)
    print(f"\n  OVERALL: {'OFF — figures suspect' if any_off else 'OK'}\n")

    if dashboard is not None:
        print("=== DASHBOARD KPIs ===")
        for k in kpi_view(dashboard):
            print(f"  {k['label']:>14}: {k['value']:>16}   ({k['comparator']})")
        donut = dashboard.get("opex_donut", {})
        if donut:
            slices = "  ".join(
                f"{s.get('label')} {fmt(to_decimal(s.get('amount')))}"
                for s in donut.get("slices", [])
            )
            print(f"  {'OpEx':>14}: {fmt(to_decimal(donut.get('total'))):>16}   ({slices})")
        print()

    if pl is not None:
        print("=== PROFITABILITY (P&L) ===")
        # Bound by identity, never by row_num: every P&L band is elastic, so
        # rows 5/7/15/24/30 name these lines on the reference chart and
        # something else on a company with a different number of expense
        # functions.
        # Revenue is a headline BUCKET, not a computed row: it carries a
        # ``heading_key``, not a ``role``.
        rev = total_figure(pl, "revenues")
        if not rev.resolved:
            rev = heading_figure(pl, "revenues")
        gm = _prefer_total(pl, "gross_margin", "gross_margin")
        oi = _prefer_total(pl, "operating_income", "operating_income")
        ni = _prefer_total(pl, "net_profit", "net_profit")
        eb = _prefer_total(pl, "ebitda", "ebitda")
        gm_pct = pct(gm.value, rev.value) if (gm.resolved and rev.resolved) else None
        print(f"  {'Revenue':>16}: {fmt_figure(rev)}")
        print(f"  {'Gross margin':>16}: {fmt_figure(gm)}"
              + (f"  ({gm_pct:.1f}%)" if gm_pct is not None else ""))
        print(f"  {'Operating inc':>16}: {fmt_figure(oi)}")
        print(f"  {'EBITDA':>16}: {fmt_figure(eb)}")
        print(f"  {'Net profit':>16}: {fmt_figure(ni)}")
        print()

    if bs is not None:
        print("=== POSITION (balance sheet) ===")
        ta = _prefer_total(bs, "total_assets", "total_assets")
        te = _prefer_total(bs, "total_equity", "total_equity")
        # equity is carried negative; flip for human reading. An UNRESOLVED
        # equity stays unresolved through the flip — negating "I don't know"
        # must not produce a number.
        te_h = Figure(
            value=-te.value if te.value is not None else None,
            unresolved_reason=te.unresolved_reason,
        )
        print(f"  {'Total assets':>16}: {fmt_figure(ta)}")
        print(f"  {'Total equity':>16}: {fmt_figure(te_h)}  (negative equity = deficit)"
              if (te_h.value is not None and te_h.value < 0)
              else f"  {'Total equity':>16}: {fmt_figure(te_h)}")
        print()

    if cf is not None:
        print("=== CASH TRAJECTORY (cash flow, direct) ===")
        totals = cf.get("totals", {})
        op = to_decimal(totals.get("net_operating"))
        inv = to_decimal(totals.get("net_investing"))
        fin = to_decimal(totals.get("net_financing"))
        chg = to_decimal(totals.get("total_change"))
        print(f"  {'Operating':>16}: {fmt(op)}")
        print(f"  {'Investing':>16}: {fmt(inv)}")
        print(f"  {'Financing':>16}: {fmt(fin)}")
        print(f"  {'Net change':>16}: {fmt(chg)}")
        print()

    return 1 if any_off else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Cross-statement position snapshot.")
    p.add_argument("--dashboard")
    p.add_argument("--pl")
    p.add_argument("--bs")
    p.add_argument("--cf")
    args = p.parse_args(argv)

    if not any((args.dashboard, args.pl, args.bs, args.cf)):
        p.error("pass at least one of --dashboard / --pl / --bs / --cf")

    return review(
        dashboard=load_json(args.dashboard) if args.dashboard else None,
        pl=load_json(args.pl) if args.pl else None,
        bs=load_json(args.bs) if args.bs else None,
        cf=load_json(args.cf) if args.cf else None,
    )


if __name__ == "__main__":
    raise SystemExit(main())
