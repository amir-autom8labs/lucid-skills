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
# skills. Self-contained: this skill bundles lucid_utils.py beside this script.
# Prepend this script's own dir so `from lucid_utils import ...` resolves to the
# sibling copy in any runtime (Claude Code, Managed Agents, claude.ai) — the whole
# skill dir, scripts included, is uploaded together, so no plugin path is needed.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lucid_utils import (  # noqa: E402  (import after sys.path tweak)
    Figure,
    fmt,
    growth,
    heading_figure,
    load_json,
    pct,
    tieout_status,
    to_decimal,
    total_figure,
)

# The headline cascade, named by the stable ``role`` each computed row carries.
#
# This USED to be a literal row list — ``[5, 6, 7, 10, 11, 12, 13, 15, 19, 24,
# 30]`` — and it was the worst positional read in these skills, because it
# straddled the elastic OpEx band: rows 10/11/12 are the first three
# operating-expense functions, so on a company with five of them this selected
# three arbitrary functions and silently dropped the other two, while 13/15/19/
# 24/30 had all shifted down by two and named the wrong lines entirely. The
# table still rendered, still footed to nothing that disagreed, and still
# called row 24 "Net Profit".
#
# Deliberately a CURATED set rather than "every row with an identity": the
# finance / other-income / tax bands also carry identities, and pulling them in
# would quietly widen what this table is. Same eleven lines as before on the
# reference chart — the OpEx block is now however many functions the tenant
# actually routes.
HEADLINE_ROLES: tuple[str, ...] = (
    "gross_margin",
    "total_opex",
    "operating_income",
    "income_before_tax",
    "net_profit",
    "ebitda",
)

# The two headline BUCKETS shown above the OpEx block, by their open
# ``heading_key``. Buckets, not bands: each is one line.
HEADLINE_HEADINGS: tuple[str, ...] = ("revenues", "cost_of_sales")

# The one band shown MEMBER-BY-MEMBER — the expense functions whose mix is the
# point of a margin analysis. Its member count is a property of the tenant.
MEMBER_BAND = "operating_expenses"


def headline_rows(report: dict) -> list[dict]:
    """The raw summary rows worth showing, selected by IDENTITY, in reading order.

    Reading order is ``row_num`` ascending — position used as presentation
    order, which is what it is for, and never as identity. Returns the raw row
    dicts (not flattened) so callers can still reach ``series``.
    """
    out = [
        row
        for row in report.get("rows", [])
        if row.get("section") == "summary"
        and (
            row.get("role") in HEADLINE_ROLES
            or row.get("heading_key") in HEADLINE_HEADINGS
            or (row.get("band_key") == MEMBER_BAND and not row.get("is_subtotal"))
        )
    ]
    out.sort(key=lambda r: (r.get("row_num") is None, r.get("row_num")))
    return out


def _revenue_rows(report: dict) -> list[dict]:
    """Every row carrying ``heading_key: revenues``. Usually one; not always.

    The ``revenues`` band is elastic like every other — its canonical capacity
    is a single row, and ``_pl_band_layout`` is explicit that capacity is "never
    a cap: a band holding more mains than that expands". A tenant routing two
    revenue mains (Product / Services) gets two rows here.

    This returns the LIST rather than a first match on purpose. An earlier cut
    of this file took ``rows[0]``, which reintroduced the exact defect this
    ticket removes, sixty lines from the ``heading_figure`` refusal that exists
    to prevent it: the ``% rev`` column read ``totals.revenues`` and was right,
    while every SERIES column was computed against only the first revenue main —
    rendering "Product revenue = 100% of revenue" in the one table a margin
    analysis exists to produce.
    """
    return [r for r in report.get("rows", []) if r.get("heading_key") == "revenues"]


def _revenue_series(report: dict) -> tuple[list, str | None]:
    """The revenue denominators for the SERIES columns, or why there are none.

    Returns ``(series, refusal)``. ``refusal`` is non-None when the band holds
    more than one revenue main: there is no single row whose ``series`` is total
    revenue, and summing the members here would be a client-side
    re-derivation of a figure the backend owns (invariant #8). The per-period
    denominator simply is not on the wire, so the columns are refused rather
    than computed against a fraction of revenue.

    The primary ``% rev`` column is unaffected — it uses ``totals.revenues``,
    which is the whole band summed once in the backend.
    """
    rows = _revenue_rows(report)
    if len(rows) > 1:
        labels = ", ".join(str(r.get("label") or "?") for r in rows)
        return [], (
            f"the revenues band holds {len(rows)} mains ({labels}), so no single row's "
            "series is total revenue — per-period % columns omitted rather than "
            "computed against one of them"
        )
    return (_series_values(rows[0]) if rows else []), None


def _row_series(row: dict | None) -> list:
    """The aligned ``series`` (multi-period columns) for one row, UNPARSED."""
    if row is None:
        return []
    series = row.get("series")
    return series if isinstance(series, list) else []


def _series_values(row: dict | None) -> list[Decimal | None]:
    """The aligned ``series`` for one row, parsed to Decimals."""
    return [to_decimal(x) for x in _row_series(row)]


def _fmt_pct(value: Decimal | None) -> str:
    return "—" if value is None else f"{value:+.1f}%"


def resolve_revenue(report: dict) -> Figure:
    """The common-size denominator, preferring the backend-computed total.

    ``totals.revenues`` is computed once in the backend, so reading it is a
    render rather than a re-derivation; the revenue bucket row is the fallback
    for a payload whose ``totals`` block was projected away.

    row-ratchet: allow — the next line QUOTES the removed defect so the reason
    survives next to the fix; it is prose, not a call. (The pytest twin of this
    scan tokenizes and so does not need the marker; the shell hook cannot.)

    This used to be ``to_decimal(totals.revenues) or find_row(report, 5)``, and
    the ``or`` was a second bug hiding inside the positional one: a legitimate
    **zero** revenue is falsy, so a company with no revenue in the period fell
    through to a positional read and reported whatever sat on row 5 — a real
    number, from an unrelated line, presented as revenue. Zero is an answer;
    only absence is a reason to look elsewhere.
    """
    figure = total_figure(report, "revenues")
    if figure.resolved and figure.value is not None:
        return figure
    return heading_figure(report, "revenues")


def common_size(report: dict, *, nonzero: bool = False) -> None:
    """Print each headline row as a % of revenue, for amount + every series column."""
    revenue = resolve_revenue(report)
    if not revenue.resolved:
        print(
            f"Revenue could not be identified ({revenue.unresolved_reason}) — "
            "common-size needs a denominator, and guessing one would invent a margin.",
            file=sys.stderr,
        )
        return
    if revenue.value is None:
        print("Revenue is missing for this period — common-size is undefined.", file=sys.stderr)
        return
    if revenue.value == 0:
        # A REAL zero, reported as one. Distinct from both branches above.
        print("Revenue is zero for this period — common-size is undefined.", file=sys.stderr)
        return
    denominator = revenue.value

    rev_series, series_refusal = _revenue_series(report)
    if series_refusal:
        print(f"note: {series_refusal}", file=sys.stderr)
    label = report.get("period", {}).get("label", "")
    header = f"{'line':<32}{'amount':>16}{'% rev':>9}"
    if rev_series:
        header += "".join(f"{f'col{i+1} %':>9}" for i in range(len(rev_series)))
    print(f"Common-size P&L — {label}  (revenue = {fmt(denominator)})")
    print(header)
    print("-" * len(header))

    for row in headline_rows(report):
        val = to_decimal(row.get("amount"))
        if nonzero and (val is None or val == 0):
            continue
        row_label = str(row.get("label") or "")
        line = f"{row_label[:31]:<32}{fmt(val):>16}{_fmt_pct(pct(val, denominator)):>9}"
        for cv, rv in zip(_series_values(row), rev_series):
            line += f"{_fmt_pct(pct(cv, rv)):>9}"
        print(line)


def growth_table(report: dict, labels: list[str] | None) -> None:
    """Print period-over-period % change of each headline row across the series."""
    sample, series_refusal = _revenue_series(report)
    if series_refusal:
        # Growth is period-over-period on each row's OWN series, so it does not
        # divide by revenue — but the width probe does, and a refused revenue
        # series must not read as "single-period payload".
        sample = _series_values(next(iter(_revenue_rows(report)), None))
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

    for row in headline_rows(report):
        series = _row_series(row)  # raw envelopes — growth() parses them
        if not series:
            continue
        label = str(row.get("label") or "")
        deltas = growth(series)  # first element is None (no prior period)
        cells = "".join(f"{_fmt_pct(d):>11}" for d in deltas)
        print(f"{label[:31]:<32}{cells}")


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
    elif status.get("unresolved"):
        # A zero delta that nobody could measure. Silence here would be the
        # false green: the P&L publishes 0 as a PLACEHOLDER while
        # ``check_unresolved`` is non-empty, so an unevaluated control must be
        # as loud as a failing one.
        reasons = "; ".join(status["unresolved"])
        print(
            f"!! TIE-OUT NOT EVALUATED: {status['kind']} could not be measured "
            f"({reasons}) — the zero delta is a placeholder, not a pass.\n",
            file=sys.stderr,
        )

    if args.growth:
        growth_table(report, args.labels.split(",") if args.labels else None)
    else:
        common_size(report, nonzero=args.nonzero)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
