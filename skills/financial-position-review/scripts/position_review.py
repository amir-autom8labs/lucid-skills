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

# Resolve the shared helper whether invoked via ${CLAUDE_PLUGIN_ROOT} or in-tree.
_HERE = os.path.dirname(os.path.abspath(__file__))
for _cand in (
    os.environ.get("CLAUDE_PLUGIN_ROOT", ""),
    os.path.join(_HERE, "..", "..", ".."),  # skills/<name>/scripts → plugin root
):
    _scripts = os.path.join(_cand, "scripts")
    if _cand and os.path.isfile(os.path.join(_scripts, "lucid_utils.py")):
        sys.path.insert(0, _scripts)
        break

# Self-contained: this skill bundles lucid_utils.py beside this script. Prepend
# this script's own dir so the import resolves in any runtime (incl. claude.ai),
# whether or not CLAUDE_PLUGIN_ROOT is set.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lucid_utils import (  # noqa: E402
    find_row,
    fmt,
    kpi_view,
    load_json,
    pct,
    tieout_status,
    to_decimal,
)


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
        rev = find_row(pl, 5)
        gm = find_row(pl, 7)
        oi = find_row(pl, 15)
        ni = find_row(pl, 24)
        eb = find_row(pl, 30)
        gm_pct = pct(gm, rev)
        print(f"  {'Revenue':>16}: {fmt(rev)}")
        print(f"  {'Gross margin':>16}: {fmt(gm)}"
              + (f"  ({gm_pct:.1f}%)" if gm_pct is not None else ""))
        print(f"  {'Operating inc':>16}: {fmt(oi)}")
        print(f"  {'EBITDA':>16}: {fmt(eb)}")
        print(f"  {'Net profit':>16}: {fmt(ni)}")
        print()

    if bs is not None:
        print("=== POSITION (balance sheet) ===")
        ta = find_row(bs, 24)
        te = find_row(bs, 57)
        # equity is carried negative; flip for human reading
        te_h = -te if te is not None else None
        print(f"  {'Total assets':>16}: {fmt(ta)}")
        print(f"  {'Total equity':>16}: {fmt(te_h)}  (negative equity = deficit)"
              if (te_h is not None and te_h < 0) else f"  {'Total equity':>16}: {fmt(te_h)}")
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
