#!/usr/bin/env python3
"""Burn-rate, runway, and cash-driver math for Lucid cash-flow payloads.

Three jobs, all built on the shared ``lucid_utils`` money parsing so the numbers
agree with every other Lucid skill:

* **burn** — average monthly *operating* burn over a trailing window. Operating
  burn (net cash used by operations) is the durable signal; total cash change is
  contaminated by one-off financing/investing items (a SAFE raise, an
  intercompany sweep), so we burn off ``net_operating`` by default.
* **runway** — current cash / monthly operating burn. ``None`` when the company
  isn't burning (burn <= 0 -> unbounded), matching Lucid's own runway KPI which
  returns ``null`` when EBITDA >= 0.
* **drivers** — rank the operating *detail* rows of one cash-flow period by
  absolute cash impact, so "what's draining cash" answers itself.

Two ways to feed it net-operating values:

* ``--periods a.json b.json c.json`` — multiple single-period cash-flow payloads
  (oldest..newest); pulls ``totals.net_operating`` from each.
* ``--net-operating -450000,-440000,-460000`` — raw values you already have.

Examples (illustrative — fictional company Acme Inc., synthetic figures)::

    # average operating burn + runway from three monthly CF files
    python burn_runway.py burn --periods jan.json feb.json mar.json --cash 8000000

    # same, from explicit values
    python burn_runway.py burn --net-operating -450000,-440000,-460000 --cash 8000000

    # rank cash drivers for one period
    python burn_runway.py drivers mar.json --top 8

Stdlib only, plus ``lucid_utils`` discovered via ``CLAUDE_PLUGIN_ROOT`` (the
plugin's ``scripts/`` dir) on ``sys.path``.
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal

# Make the plugin's shared helper importable. CLAUDE_PLUGIN_ROOT is set when the
# skill runs inside Claude Code; fall back to the repo layout for local runs.
_PLUGIN_ROOT = os.environ.get(
    "CLAUDE_PLUGIN_ROOT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")),
)
sys.path.insert(0, os.path.join(_PLUGIN_ROOT, "scripts"))
# Self-contained: this skill bundles lucid_utils.py beside this script. Prepend
# this script's own dir LAST so it wins on sys.path — the import then resolves in
# any runtime (incl. claude.ai), whether or not CLAUDE_PLUGIN_ROOT is set.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lucid_utils import (  # noqa: E402  (import after sys.path tweak)
    fmt,
    load_json,
    report_rows,
    runway_months,
    to_decimal,
)


# --------------------------------------------------------------------------- #
# Burn + runway
# --------------------------------------------------------------------------- #
def net_operating_from_files(paths: list[str]) -> list[Decimal | None]:
    """Pull ``totals.net_operating`` from each single-period cash-flow file."""
    out: list[Decimal | None] = []
    for path in paths:
        report = load_json(path)
        totals = report.get("totals", {}) if isinstance(report, dict) else {}
        out.append(to_decimal(totals.get("net_operating")))
    return out


def average_monthly_burn(net_operating: list[Decimal | None]) -> Decimal | None:
    """Average monthly burn (positive = cash consumed) over the supplied months.

    Burn is the negation of net operating cash flow: a -$450,000 operating month
    is +$450,000 of burn. Months with no data (``None``) are skipped, not treated
    as zero, so a gap in the books doesn't silently understate burn. Returns
    ``None`` if there's nothing to average.
    """
    vals = [v for v in net_operating if v is not None]
    if not vals:
        return None
    total_operating = sum(vals, Decimal(0))
    avg_operating = total_operating / Decimal(len(vals))
    return -avg_operating  # flip sign: outflow -> positive burn


def burn_and_runway(
    net_operating: list[Decimal | None], cash: Decimal | None
) -> dict[str, object]:
    """Bundle the trailing-window burn and the derived runway."""
    monthly_burn = average_monthly_burn(net_operating)
    months = runway_months(cash, monthly_burn)
    return {
        "months_used": len([v for v in net_operating if v is not None]),
        "net_operating": net_operating,
        "monthly_operating_burn": monthly_burn,
        "current_cash": cash,
        "runway_months": months,
    }


# --------------------------------------------------------------------------- #
# Cash drivers
# --------------------------------------------------------------------------- #
def cash_drivers(cf: dict, *, top: int | None = None) -> list[dict[str, object]]:
    """Rank operating *detail* rows of one cash-flow period by |cash impact|.

    Skips subtotal / net-section rows (they'd double-count) and zero rows, then
    sorts by absolute amount so the biggest cash movers -- inflows and outflows
    alike -- surface first. The ``ref`` rows (COGS/R&D/S&M/G&A...) carry a
    ``group_key``; their per-line detail lives in the ``breakdown`` section linked
    by ``parent``, so a reader can drill from the headline driver into its notes.
    """
    rows = report_rows(cf, section="operating", details_only=True, nonzero=True)
    rows.sort(key=lambda r: abs(r["value"]) if r["value"] is not None else Decimal(0), reverse=True)
    drivers = [
        {
            "row": r["row"],
            "label": r["label"],
            "value": r["value"],
            "direction": "inflow" if (r["value"] or 0) > 0 else "outflow",
        }
        for r in rows
    ]
    return drivers[:top] if top else drivers


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _parse_values(csv: str) -> list[Decimal | None]:
    out: list[Decimal | None] = []
    for tok in csv.split(","):
        tok = tok.strip()
        if not tok:
            continue
        out.append(to_decimal(tok))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_burn = sub.add_parser("burn", help="average monthly operating burn + runway")
    src = p_burn.add_mutually_exclusive_group(required=True)
    src.add_argument("--periods", nargs="+", metavar="CF.json", help="single-period CF files, oldest..newest")
    src.add_argument("--net-operating", metavar="V1,V2,...", help="explicit net_operating values")
    p_burn.add_argument("--cash", required=True, help="current cash on hand (number or envelope amount)")

    p_drv = sub.add_parser("drivers", help="rank operating cash drivers for one period")
    p_drv.add_argument("file")
    p_drv.add_argument("--top", type=int)

    args = parser.parse_args(argv)

    if args.cmd == "burn":
        if args.periods:
            net_op = net_operating_from_files(args.periods)
        else:
            net_op = _parse_values(args.net_operating)
        cash = to_decimal(args.cash)
        result = burn_and_runway(net_op, cash)

        print(f"  months used            : {result['months_used']}")
        series = ", ".join(fmt(v) for v in net_op)
        print(f"  net operating / month  : {series}")
        burn = result["monthly_operating_burn"]
        print(f"  avg monthly op. burn   : {fmt(burn if isinstance(burn, Decimal) else None)}")
        print(f"  current cash           : {fmt(cash)}")
        months = result["runway_months"]
        if isinstance(months, Decimal):
            print(f"  runway                 : {months:.1f} months")
        else:
            print("  runway                 : unbounded (not burning) / unknown")
        return 0

    if args.cmd == "drivers":
        cf = load_json(args.file)
        for d in cash_drivers(cf, top=args.top):
            arrow = "in " if d["direction"] == "inflow" else "out"
            val = d["value"]
            print(f"  [{d['row']:>4}] {arrow} {fmt(val if isinstance(val, Decimal) else None):>16}  {d['label']}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
