#!/usr/bin/env python3
"""Shared helpers for consuming Lucid MCP report payloads.

Every Lucid report tool returns money as a self-describing envelope::

    {"amount": "1234567.89", "currency": "USD", "units": "major"}

``amount`` is already in **major units** (dollars), as an exact decimal string —
never divide by 100. Some fields are plain numbers instead (counts, dashboard
``bps`` / ``months`` units, ratios), and some are ``null`` ("no data"). The whole
point of this module is to read all of those correctly and identically across
every analysis skill, so a P&L margin and a board-pack figure never disagree
because two skills parsed the same envelope two different ways.

Two ways to use it:

* **Import it** in a script you write for an analysis:
  ``from lucid_utils import to_decimal, report_rows, fmt`` ...
* **Run it as a CLI** to pull compact, already-parsed tables out of a (possibly
  huge, spilled-to-file) tool result without loading the raw JSON into context::

      python lucid_utils.py rows report.json --section summary --nonzero
      python lucid_utils.py totals report.json
      python lucid_utils.py kpis dashboard.json
      python lucid_utils.py bva bva.json --top 10

Stdlib only — no third-party dependencies, so it runs anywhere Python 3 does.
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation
from typing import Any


# --------------------------------------------------------------------------- #
# Parsing the money envelope
# --------------------------------------------------------------------------- #
def to_decimal(field: Any) -> Decimal | None:
    """Return the numeric value of a Lucid field as a :class:`Decimal`.

    Handles all four shapes a money-ish field can take on the wire:

    * the envelope ``{"amount": "1234.56", ...}`` → ``Decimal("1234.56")``
    * a plain number (``17``, ``-3966``, ``78.2``) → ``Decimal`` of it
    * a numeric string (``"1234.56"``) → ``Decimal`` of it
    * ``None`` (a genuine "no data" sentinel) → ``None``

    Returning ``None`` rather than ``0`` for missing data is deliberate: a real
    zero and "this period has no backing data" mean different things to a CFO,
    and collapsing them hides gaps in the books.
    """
    if field is None:
        return None
    if isinstance(field, bool):  # bool is an int subclass — never a money value
        return None
    if isinstance(field, (int, float)):
        return Decimal(str(field))
    if isinstance(field, dict) and "amount" in field:
        return to_decimal(field["amount"])
    if isinstance(field, str):
        try:
            return Decimal(field)
        except InvalidOperation:
            return None
    return None


def currency_of(field: Any, default: str = "USD") -> str:
    """Best-effort presentation currency for a field (defaults to USD)."""
    if isinstance(field, dict) and field.get("currency"):
        return str(field["currency"])
    return default


def fmt(value: Decimal | int | float | None, currency: str = "USD", dp: int = 0) -> str:
    """Format a number the way a CFO reads it: ``$1,234,567`` (thousands, signed).

    ``dp`` controls decimal places (0 for headline figures, 2 for unit economics).
    ``None`` renders as ``"—"`` so missing data is visible, not silently zero.
    """
    if value is None:
        return "—"
    dec = value if isinstance(value, Decimal) else Decimal(str(value))
    sign = "-" if dec < 0 else ""
    body = f"{abs(dec):,.{dp}f}"
    symbol = {"USD": "$", "EUR": "€", "GBP": "£", "ILS": "₪"}.get(currency, currency + " ")
    return f"{sign}{symbol}{body}"


# --------------------------------------------------------------------------- #
# Ratios and derived figures
# --------------------------------------------------------------------------- #
def pct(numer: Decimal | None, denom: Decimal | None) -> Decimal | None:
    """``numer / denom`` as a percentage, or ``None`` if it is undefined."""
    if numer is None or denom is None or denom == 0:
        return None
    return (numer / denom) * Decimal(100)


def bps_to_pct(bps: Any) -> Decimal | None:
    """Dashboard ``bps`` unit → percent. ``7820`` → ``78.20`` (basis-points ×100)."""
    val = to_decimal(bps)
    return None if val is None else val / Decimal(100)


def growth(series: list[Any]) -> list[Decimal | None]:
    """Period-over-period % change for a series of money envelopes / numbers.

    The first element has no prior period, so it is ``None``; any step off a
    zero or missing base is ``None`` (the change is undefined, not "infinite").
    """
    vals = [to_decimal(x) for x in series]
    out: list[Decimal | None] = [None]
    for prev, cur in zip(vals, vals[1:]):
        out.append(pct(cur - prev, abs(prev)) if (prev not in (None, Decimal(0)) and cur is not None) else None)
    return out


def runway_months(cash: Decimal | None, monthly_burn: Decimal | None) -> Decimal | None:
    """Months of cash left at a given monthly burn.

    ``monthly_burn`` is a positive number of dollars consumed per month. Returns
    ``None`` when the company isn't burning (burn ≤ 0 → runway is unbounded) or
    cash is unknown — matching how Lucid's own runway KPI reports ``null`` when
    EBITDA ≥ 0.
    """
    if cash is None or monthly_burn is None or monthly_burn <= 0:
        return None
    return cash / monthly_burn


# --------------------------------------------------------------------------- #
# Loading payloads (including large spilled tool results)
# --------------------------------------------------------------------------- #
def load_json(source: str | dict) -> Any:
    """Load a report from a dict, a file path, or ``-`` (stdin).

    Large tool results are spilled to a file by the harness; pass that path here
    instead of pasting the JSON back into context.
    """
    if isinstance(source, dict):
        return source
    if source == "-":
        return json.load(sys.stdin)
    with open(source, encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------- #
# Row helpers — TB / BS / PL / CF / BVA all expose a ``rows`` list
# --------------------------------------------------------------------------- #
def _row_amount(row: dict, column: str) -> Decimal | None:
    """Pull the money column off a row, trying common keys in order."""
    for key in ([column] if column else []) + ["amount", "balance", "actual"]:
        if key in row:
            return to_decimal(row[key])
    return None


def report_rows(
    report: dict,
    *,
    section: str | None = None,
    column: str = "amount",
    subtotals_only: bool = False,
    details_only: bool = False,
    nonzero: bool = False,
) -> list[dict[str, Any]]:
    """Flatten a report's ``rows`` into compact ``{row, label, section, value}`` dicts.

    Filters keep the output small enough to reason over directly:

    * ``section`` — keep one section (e.g. ``"summary"``, ``"assets"``, ``"operating"``).
    * ``subtotals_only`` / ``details_only`` — headline lines vs leaf detail.
    * ``nonzero`` — drop zero / no-data rows, which dominate a sparse template.
    """
    out: list[dict[str, Any]] = []
    for row in report.get("rows", []):
        if section is not None and row.get("section") != section:
            continue
        is_sub = bool(row.get("is_subtotal"))
        if subtotals_only and not is_sub:
            continue
        if details_only and is_sub:
            continue
        value = _row_amount(row, column)
        if nonzero and (value is None or value == 0):
            continue
        out.append(
            {
                "row": row.get("row_num"),
                "label": row.get("label"),
                "section": row.get("section"),
                "is_subtotal": is_sub,
                "value": value,
            }
        )
    return out


def find_row(report: dict, row_num: int, column: str = "amount") -> Decimal | None:
    """Value of a specific template row (e.g. P&L row 24 = Net Profit)."""
    for row in report.get("rows", []):
        if row.get("row_num") == row_num:
            return _row_amount(row, column)
    return None


# --------------------------------------------------------------------------- #
# Report-specific views
# --------------------------------------------------------------------------- #
def kpi_view(dashboard: dict) -> list[dict[str, Any]]:
    """Normalize dashboard KPIs into human-readable rows, honouring each unit.

    Dashboard KPIs mix units on purpose: cash / revenue are money envelopes,
    runway is integer ``months``, gross-margin is ``bps`` (×100). Reading them
    all as dollars is the classic mistake — this resolves each by its ``unit``.
    """
    out: list[dict[str, Any]] = []
    for kpi in dashboard.get("kpis", []):
        unit = kpi.get("unit")
        amount = kpi.get("amount")
        if unit == "cents":
            display = fmt(to_decimal(amount), currency_of(amount))
        elif unit == "bps":
            p = bps_to_pct(amount)
            display = "—" if p is None else f"{p:.2f}%"
        elif unit == "months":
            display = "—" if amount is None else f"{amount} mo"
        else:
            display = str(amount)
        out.append(
            {
                "kind": kpi.get("kind"),
                "label": kpi.get("label"),
                "value": display,
                "comparator": kpi.get("comparator"),
            }
        )
    return out


def variance_table(bva: dict, *, top: int | None = None) -> list[dict[str, Any]]:
    """Rank BVA rows by absolute variance — the "where are we off plan" view.

    Returns ``{row, label, actual, budget, variance, variance_pct}`` sorted by
    the size of the miss, so the material variances surface first regardless of
    sign.
    """
    rows: list[dict[str, Any]] = []
    for row in bva.get("rows", []):
        var = to_decimal(row.get("variance"))
        if var is None:
            continue
        rows.append(
            {
                "row": row.get("row_num"),
                "label": row.get("label"),
                "actual": to_decimal(row.get("actual")),
                "budget": to_decimal(row.get("budget")),
                "variance": var,
                "variance_pct": row.get("variance_pct"),
                "is_subtotal": bool(row.get("is_subtotal")),
            }
        )
    rows.sort(key=lambda r: abs(r["variance"]), reverse=True)
    return rows[:top] if top else rows


def tieout_status(report: dict) -> dict[str, Any]:
    """Summarize whatever reconciliation check a report carries.

    A CFO assistant should never present numbers without confirming the books
    tie out. Different reports expose the check differently; this normalizes them
    to ``{ok: bool, delta: Decimal|None, kind: str}``.
    """
    totals = report.get("totals", {})
    for key in ("balance_check_delta", "check_delta"):
        if key in totals:
            d = to_decimal(totals[key])
            return {"ok": d == 0, "delta": d, "kind": key}
    if "tieout" in report:
        d = to_decimal(report["tieout"].get("period_delta"))
        return {"ok": d == 0, "delta": d, "kind": "cf_period_delta"}
    if "tie_out_ok" in report:
        return {"ok": bool(report["tie_out_ok"]), "delta": None, "kind": "tie_out_ok"}
    return {"ok": None, "delta": None, "kind": "none"}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _print_rows(rows: list[dict[str, Any]]) -> None:
    for r in rows:
        val = r.get("value")
        marker = "  ▸" if r.get("is_subtotal") else "   "
        print(f"{marker} [{r.get('row'):>4}] {fmt(val):>16}  {r.get('label')}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse Lucid MCP report payloads.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_rows = sub.add_parser("rows", help="filtered row table")
    p_rows.add_argument("file")
    p_rows.add_argument("--section")
    p_rows.add_argument("--column", default="amount")
    p_rows.add_argument("--subtotals", action="store_true")
    p_rows.add_argument("--details", action="store_true")
    p_rows.add_argument("--nonzero", action="store_true")

    p_tot = sub.add_parser("totals", help="totals block + tie-out status")
    p_tot.add_argument("file")

    p_kpi = sub.add_parser("kpis", help="dashboard KPIs, unit-aware")
    p_kpi.add_argument("file")

    p_bva = sub.add_parser("bva", help="budget-vs-actual variance table")
    p_bva.add_argument("file")
    p_bva.add_argument("--top", type=int)

    args = parser.parse_args(argv)
    report = load_json(args.file)

    if args.cmd == "rows":
        _print_rows(
            report_rows(
                report,
                section=args.section,
                column=args.column,
                subtotals_only=args.subtotals,
                details_only=args.details,
                nonzero=args.nonzero,
            )
        )
    elif args.cmd == "totals":
        for key, val in report.get("totals", {}).items():
            d = to_decimal(val)
            if d is not None:
                print(f"{key:>28}: {fmt(d):>16}")
        status = tieout_status(report)
        flag = {True: "OK", False: "OFF", None: "n/a"}[status["ok"]]
        print(f"{'tie-out':>28}: {flag}  (delta {fmt(status['delta'])}, {status['kind']})")
    elif args.cmd == "kpis":
        for k in kpi_view(report):
            print(f"  {k['label']:>14}: {k['value']:>16}   ({k['comparator']})")
    elif args.cmd == "bva":
        for r in variance_table(report, top=args.top):
            vp = r["variance_pct"]
            vp_s = "—" if vp is None else f"{vp * 100:+.1f}%"
            print(
                f"  [{r['row']:>4}] {r['label']:<40} "
                f"act {fmt(r['actual']):>14}  bud {fmt(r['budget']):>14}  "
                f"var {fmt(r['variance']):>14} ({vp_s})"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
