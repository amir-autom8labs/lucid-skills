#!/usr/bin/env python3
"""Build a common-size P&L (and optional growth) table from a ``get_pl`` payload.

Common-size restates every income-statement line as a **percentage of revenue**,
which is how you compare a P&L across months, quarters, or against peers without
a 50x company-size difference drowning out the signal. A line that is "up $200k"
is meaningless until you know whether revenue tripled or halved underneath it;
``line / revenue`` answers that.

Two views:

* **common-size** (default) — each summary row as a % of that period's revenue,
  for the primary ``amount`` and for every aligned ``series`` column when present.
* **growth** (``--growth``) — period-over-period % change of each row across the
  ``series``, the MoM/QoQ/YoY trend view. Requires a multi-period payload (one
  fetched with ``periods=`` — preferred, so columns are labelled — or ``compare``).

Works on a single-period or multi-period payload, read from a file path (including
a spilled-to-file tool result) or ``-`` for stdin. Stdlib only; reuses
``lucid_utils`` so money parsing and ratios match every other Lucid skill::

    python common_size.py pl.json
    python common_size.py pl.json --growth --labels 2025-01,2025-02,2025-03
    mcp_result_as_json | python common_size.py - --nonzero
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal

# Reuse the shared envelope/ratio helpers so figures never disagree between
# skills. ``CLAUDE_PLUGIN_ROOT`` is set when running inside the plugin; fall back
# to the repo layout (this file lives at skills/<skill>/scripts/).
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
    find_row,
    fmt,
    growth,
    load_json,
    pct,
    report_rows,
    tieout_status,
    to_decimal,
)

# Summary-section rows worth showing on a margin analysis, in reading order.
HEADLINE_ROWS = [5, 6, 7, 10, 11, 12, 13, 15, 19, 24, 30]


def _raw_series(report: dict, row_num: int) -> list:
    """The aligned ``series`` (multi-period columns) for one row, UNPARSED."""
    for row in report.get("rows", []):
        if row.get("row_num") == row_num:
            series = row.get("series")
            return series if isinstance(series, list) else []
    return []


def _series_values(report: dict, row_num: int) -> list[Decimal | None]:
    """The aligned ``series`` for one template row, parsed to Decimals."""
    return [to_decimal(x) for x in _raw_series(report, row_num)]


def _fmt_pct(value: Decimal | None) -> str:
    return "—" if value is None else f"{value:+.1f}%"


def common_size(report: dict, *, nonzero: bool = False) -> None:
    """Print each summary row as a % of revenue, for amount + every series column."""
    revenue = to_decimal(report.get("totals", {}).get("revenues")) or find_row(report, 5)
    if revenue in (None, Decimal(0)):
        print("Revenue is zero or missing — common-size is undefined.", file=sys.stderr)
        return

    rev_series = _series_values(report, 5)
    label = report.get("period", {}).get("label", "")
    header = f"{'line':<32}{'amount':>16}{'% rev':>9}"
    if rev_series:
        header += "".join(f"{f'col{i+1} %':>9}" for i in range(len(rev_series)))
    print(f"Common-size P&L — {label}  (revenue = {fmt(revenue)})")
    print(header)
    print("-" * len(header))

    for r in report_rows(report, section="summary"):
        if r["row"] not in HEADLINE_ROWS:
            continue
        val = r["value"]
        if nonzero and (val is None or val == 0):
            continue
        line = f"{(r['label'] or '')[:31]:<32}{fmt(val):>16}{_fmt_pct(pct(val, revenue)):>9}"
        col = _series_values(report, r["row"])
        for cv, rv in zip(col, rev_series):
            line += f"{_fmt_pct(pct(cv, rv)):>9}"
        print(line)


def growth_table(report: dict, labels: list[str] | None) -> None:
    """Print period-over-period % change of each headline row across the series."""
    sample = _series_values(report, 5)
    if len(sample) < 2:
        print(
            "Growth needs a multi-period payload (fetch with periods= or compare).",
            file=sys.stderr,
        )
        return

    width = len(sample)
    cols = labels if labels and len(labels) == width else [f"col{i+1}" for i in range(width)]
    if labels and len(labels) != width:
        print(
            f"warning: {len(labels)} labels for {width} columns — using positional headers.",
            file=sys.stderr,
        )
    print("Period-over-period growth (% change vs prior column)")
    print(f"{'line':<32}" + "".join(f"{c:>11}" for c in cols))
    print("-" * (32 + 11 * width))

    for row_num in HEADLINE_ROWS:
        series = _raw_series(report, row_num)  # raw envelopes — growth() parses them
        if not series:
            continue
        label = next(
            (r["label"] for r in report_rows(report, section="summary") if r["row"] == row_num),
            str(row_num),
        )
        deltas = growth(series)  # first element is None (no prior period)
        cells = "".join(f"{_fmt_pct(d):>11}" for d in deltas)
        print(f"{(label or '')[:31]:<32}{cells}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", help="get_pl payload: path, or '-' for stdin")
    parser.add_argument("--growth", action="store_true", help="period-over-period growth table")
    parser.add_argument("--nonzero", action="store_true", help="drop zero rows (common-size)")
    parser.add_argument("--labels", help="comma-separated column labels for growth")
    args = parser.parse_args(argv)

    report = load_json(args.file)

    status = tieout_status(report)
    if status["ok"] is False:
        print(
            f"!! TIE-OUT OFF: {status['kind']} delta {fmt(status['delta'])} "
            "— figures are suspect.\n",
            file=sys.stderr,
        )

    if args.growth:
        growth_table(report, args.labels.split(",") if args.labels else None)
    else:
        common_size(report, nonzero=args.nonzero)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
