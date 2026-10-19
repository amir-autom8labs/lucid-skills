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
from dataclasses import dataclass
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
    """Flatten a report's ``rows`` into compact ``{row, label, section, is_subtotal,
    value}`` dicts.

    Filters keep the output small enough to reason over directly:

    * ``section`` — keep one section (e.g. ``"summary"``, ``"assets"``, ``"operating"``).
    * ``subtotals_only`` / ``details_only`` — headline lines vs leaf detail.
    * ``nonzero`` — drop zero / no-data rows, which dominate a sparse template.

    A row the backend marks ``uncomputed`` — one it computes no figure for —
    gets ``value: None`` plus ``"uncomputed": True``, so the line renders with
    no number. ``nonzero=True`` drops such a row before that: its raw value is
    zero or absent, and the filter takes either.
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
        # A row the backend computes no figure for gets ``value: None`` — the
        # same "no number here" every other unknown uses, so a renderer that
        # never heard of the marker prints ``fmt(None)`` = "—" rather than the
        # structural zero. ``uncomputed`` rides along as the REASON, not as the
        # only defence.
        uncomputed = bool(row.get("uncomputed"))
        entry: dict[str, Any] = {
            "row": row.get("row_num"),
            "label": row.get("label"),
            "section": row.get("section"),
            "is_subtotal": is_sub,
            "value": None if uncomputed else value,
        }
        if uncomputed:
            entry["uncomputed"] = True
        # The projected part of the figure (an estimate of entries not booked
        # yet, in an open month). Present only when non-zero, so a renderer can
        # disclose it next to ``value``.
        # Only the ``amount`` column has a projected part on the wire.
        projected = (
            None if uncomputed or column != "amount" else to_decimal(row.get("projected"))
        )
        if projected:
            entry["projected"] = projected
        out.append(entry)
    return out


def find_row(report: dict, row_num: int, column: str = "amount") -> Decimal | None:
    """Value of a specific template row, BY POSITION — almost never what you want.

    ``row_num`` is a **coordinate, not an identity**. Every P&L band is elastic
    (one row per operating-expense main the tenant routes, everything below it
    shifted down by the excess) and the Balance Sheet's asset rows come out in
    whatever order that company's routing produced. So a literal ``row_num``
    copied off one company names a different line on the next, silently and
    with a plausible number attached.

    A pinned ``row_num`` is only ever right on the chart it was read from, which
    is why every pin in these skills survived review: they were all read off
    the one reference chart the canonical skeleton was traced from, and that
    chart keeps returning the expected value forever.

    Use the identity resolvers below instead — :func:`role_figure`,
    :func:`total_figure`, :func:`heading_figure`, :func:`band_member_rows`.
    This function stays for the one legitimate case: a ``row_num`` read out of
    the very payload you are holding (a caller nominating a row it just saw),
    where the coordinate never outlives the frame it came from.
    """
    for row in report.get("rows", []):
        if row.get("row_num") == row_num:
            return _row_amount(row, column)
    return None


# --------------------------------------------------------------------------- #
# Stable row identity — how to name a statement line without its position
# --------------------------------------------------------------------------- #
# The wire carries three position-free identities, and which one names a given
# line follows from what that line IS:
#
# * ``role``        — a COMPUTED / scaffold row: the P&L's ``net_profit`` /
#                     ``ebitda`` / ``gross_margin`` / ``total_opex``, the
#                     Balance Sheet's ``total_assets`` / ``total_equity`` /
#                     ``total_current_liabilities`` / ``pl_loss_profit`` ...
# * ``heading_key`` — a HEADLINE BUCKET row (``revenues``, ``cost_of_sales``):
#                     OPEN vocabulary, because a tenant may mint its own.
# * ``band_key``    — CLOSED arithmetic: which subtotal this row's balance foots
#                     into. A band legitimately holds SEVERAL rows, so it names
#                     a SET (use :func:`band_member_rows`), never a single line.
#
# And a fourth, which beats all three when it exists: the report's own
# ``totals`` block. Those figures are computed once in the backend and every
# consumer renders them verbatim — so when a number is in ``totals``, read it
# from there rather than resolving the row that displays it.


@dataclass(frozen=True)
class Figure:
    """One figure the wire could name, or an explicit statement that it could not.

    Three states, and keeping them apart is the whole point of this type:

    * **resolved, with a value** — ``value`` is the number; render it.
    * **resolved, no data** — ``value is None`` and ``unresolved_reason is
      None``: the line exists and the period has nothing in it. Render "—".
    * **unresolved** — ``unresolved_reason`` says why the identity could not be
      found at all. Render "not identified", and **never** a ``0``.

    That last distinction is the reason this is a type rather than a
    ``Decimal | None``. A ``0`` substituted for "I don't know" is
    indistinguishable from a measured zero, so it reads as a finding: a board
    pack that states cash is zero because it could not find the cash line is
    worse than one that says it could not find the cash line.
    """

    value: Decimal | None = None
    unresolved_reason: str | None = None

    @property
    def resolved(self) -> bool:
        """Did the identity resolve? (Says nothing about whether it has data.)"""
        return self.unresolved_reason is None

    def __bool__(self) -> bool:
        """Truthy only when resolved AND carrying data.

        Defined explicitly because the default (always truthy) invites the
        ``figure or fallback`` idiom, and a legitimate **zero** must not fall
        through to a fallback — that is the exact bug this module's
        ``common_size`` caller shipped. Prefer ``.resolved`` / ``is None``
        checks; this exists so a bare truth test is at least not wrong.
        """
        return self.resolved and self.value is not None


def _has_column(report: dict, key: str) -> bool:
    """Does ANY row in this payload carry ``key``?

    Needed because "no row has this role" and "this payload has no ``role``
    column at all" are different failures with different fixes, and the MCP
    relay can produce the second on its own: ``compact_report`` drops a column
    that is ``None`` across a whole row array, and a ``fields=[...]`` request
    projects columns away. Reporting both as "role absent" would send a reader
    hunting a template bug when the real answer is "ask for the column".
    """
    return any(key in row for row in report.get("rows", []))


def role_projected(report: dict, role: str) -> Decimal | None:
    """The projected part of the row carrying ``role``, or ``None`` when it has none.

    Read from the row's own ``projected`` field (the backend foots it on
    subtotals); never derived.
    """
    for row in report.get("rows", []):
        if row.get("role") == role:
            return to_decimal(row.get("projected")) or None
    return None


def role_figure(report: dict, role: str, column: str = "amount") -> Figure:
    """The value of the row carrying ``role`` — the identity of a computed row.

    ``role`` is the persisted ``report_templates.role``, the stable name of a
    scaffold row (``net_profit``, ``ebitda``, ``total_assets``,
    ``total_current_liabilities``, ...). Bind to it, never to a ``row_num``.

    A role a template genuinely never stamped (``equity_earnings`` is absent
    from every generated template) resolves to an explicit reason, not a zero.
    So does a role whose row ``get_pl`` / ``get_consolidated_report`` do not return
    (``pct_gross_margin``, ``adjusted_net_profit``, ``total_expenses``,
    ``depreciation``): the reason is then "no row carries role …". A row the
    backend marks ``uncomputed`` resolves to its own reason: its cells are
    structural zeros written without measuring anything, and a ``0`` here would
    read as a finding.
    """
    if not _has_column(report, "role"):
        return Figure(
            unresolved_reason=(
                f"this payload carries no 'role' column, so the {role!r} row cannot be "
                "identified — request it in `fields`, or drop the projection"
            )
        )
    for row in report.get("rows", []):
        if row.get("role") == role:
            if row.get("uncomputed"):
                return Figure(
                    unresolved_reason=(
                        f"the {role!r} row carries no figure — the backend does not "
                        "compute it, so its cells are structural zeros"
                    )
                )
            return Figure(value=_row_amount(row, column))
    return Figure(unresolved_reason=f"no row carries role {role!r}")


def total_figure(report: dict, key: str) -> Figure:
    """A figure from the report's own ``totals`` block — the preferred source.

    Everything in ``totals`` was computed once in the backend, so reading it
    here is a render, not a re-derivation. Prefer this over resolving the row
    that displays the same number: it survives ``density="totals"``, so a
    question that needs only headline figures costs one small payload instead
    of the whole statement.
    """
    totals = report.get("totals")
    if not isinstance(totals, dict):
        return Figure(unresolved_reason="this payload carries no 'totals' block")
    if key not in totals:
        return Figure(unresolved_reason=f"'totals' carries no {key!r}")
    return Figure(value=to_decimal(totals[key]))


def heading_figure(report: dict, heading_key: str, column: str = "amount") -> Figure:
    """The value of the headline BUCKET row carrying ``heading_key``.

    The heading vocabulary is OPEN — a tenant may route to a heading of its own
    minting — so an unknown key is a legitimate answer here, never a reason to
    reject the payload.

    ``heading_key`` alone is NEVER a row identity in general (a band may hold
    several rows that share one); it is only single-valued for the *headline
    bucket* rows this resolves. For the members of a band, use
    :func:`band_member_rows`.
    """
    if not _has_column(report, "heading_key"):
        return Figure(
            unresolved_reason=(
                f"this payload carries no 'heading_key' column, so the {heading_key!r} "
                "line cannot be identified"
            )
        )
    matches = [r for r in report.get("rows", []) if r.get("heading_key") == heading_key]
    if not matches:
        return Figure(unresolved_reason=f"no row carries heading_key {heading_key!r}")
    if len(matches) > 1:
        # Deliberately a refusal rather than a pick or a sum. Several rows under
        # one heading means this is a band, not a bucket, and summing them here
        # would be a client-side re-derivation of a subtotal the backend
        # already publishes — read that subtotal's `role` instead.
        return Figure(
            unresolved_reason=(
                f"{len(matches)} rows carry heading_key {heading_key!r} — that is a band, "
                "not a single line; read its subtotal's role, or use band_member_rows()"
            )
        )
    return Figure(value=_row_amount(matches[0], column))


def band_member_rows(
    report: dict, band_key: str, *, column: str = "amount"
) -> list[dict[str, Any]]:
    """The MEMBER rows of one band — e.g. every operating-expense function.

    A band is elastic by design: three members on the reference chart, five on a
    company with five expense functions, none on one that routes none. So this
    returns a LIST whose length is a property of the tenant, and a caller must
    map over it — never assume a count, an order, or a label.

    Subtotal rows are excluded: a band's own subtotal carries a ``role``
    (``total_opex``) and is the band's total, not a member of it. Sorted by
    ``row_num`` so the order matches the statement as rendered — position used
    as presentation order, which is what it is for, and never as identity.
    """
    out = [
        {
            "row": r.get("row_num"),
            "label": r.get("label"),
            "band_key": r.get("band_key"),
            "heading_key": r.get("heading_key"),
            "value": _row_amount(r, column),
        }
        for r in report.get("rows", [])
        if r.get("band_key") == band_key and not r.get("is_subtotal")
    ]
    out.sort(key=lambda r: (r["row"] is None, r["row"]))
    return out


def bs_cash(report: dict) -> Figure:
    """The Balance Sheet's own cash figure, from ``totals.cash``.

    Cash is named here rather than by a row number because a BS leaf carries no
    identity on the wire: ``row_num`` 5 is whichever asset the tenant's routing
    ordered first. Cash is the balance of the accounts flagged ``is_cash_pool``,
    counted per account wherever the statement presents them, so it is not in
    general the sum of any set of statement rows. The backend publishes the
    figure; render it and never re-sum rows, ``row_nums`` or ``components``
    (invariant #8).

    Two caveats ride with it and BOTH must reach the reader:

    * ``unresolved_reason`` — no figure at all. This returns an unresolved
      :class:`Figure`, so ``fmt_figure`` prints "not identified".
    * ``disclosures`` — the figure stands, and it differs from the statement's
      cash rows: part of it is presented outside a cash class (under another
      class, or on no Balance Sheet row), or a cash class also holds accounts
      that are not cash. Read them with :func:`bs_cash_disclosures` and show
      them beside the number; :func:`bs_cash_reconciliation` gives the amounts
      behind each "includes" clause.
    """
    totals = report.get("totals")
    if not isinstance(totals, dict):
        return Figure(unresolved_reason="this payload carries no 'totals' block")
    cash = totals.get("cash")
    if not isinstance(cash, dict):
        return Figure(
            unresolved_reason=(
                "this payload carries no 'totals.cash' block — it predates the "
                "field, so the cash line cannot be identified"
            )
        )
    reason = cash.get("unresolved_reason")
    if reason:
        return Figure(unresolved_reason=str(reason))
    amount = to_decimal(cash.get("amount"))
    if amount is None:
        # The wire contract is `amount is None` IFF `unresolved_reason` is set.
        # If both are null the contract is broken upstream, and returning a
        # RESOLVED Figure(None) here would render "—" — "the line is there and
        # the period is empty", a positive claim about a payload that made no
        # claim at all. Refuse instead of inventing the friendlier reading.
        return Figure(
            unresolved_reason=(
                "totals.cash carries neither an amount nor a reason — the payload "
                "violates the wire contract, so cash is unknown"
            )
        )
    return Figure(value=amount)


def bs_cash_disclosures(report: dict) -> list[str]:
    """Caption-length clauses saying where the cash figure and the cash rows part.

    "includes 2 account(s) presented under Other receivables", or "… on no
    Balance Sheet row", for cash presented outside a cash class; "excludes 1
    account(s) in Cash and Cash equivalents not ticked as cash" for a cash
    class that also holds accounts that are not cash. Empty when there is no
    clause of either kind: no cash presented outside a cash class with a
    non-zero amount, and no cash class whose accounts that are not cash hold a
    non-zero total. A caller that prints the cash figure MUST print these
    beside it — see :func:`bs_cash`.
    """
    totals = report.get("totals")
    cash = totals.get("cash") if isinstance(totals, dict) else None
    if not isinstance(cash, dict):
        return []
    disclosures = cash.get("disclosures")
    return [str(d) for d in disclosures] if isinstance(disclosures, list) else []


def bs_cash_reconciliation(report: dict) -> list[dict[str, Any]]:
    """The part of cash presented outside a cash class, from ``totals.cash.components``.

    One entry per component that is not a cash class and holds a non-zero
    amount, in wire order::

        {"main_class": "Other receivables",   # None: on no Balance Sheet row
         "amount": Decimal("22500.53"),
         "accounts": [{"account_no": "10291", "name": "PayPal", "amount": Decimal(...)}]}

    Every figure is read off the wire; nothing is summed here. Empty when all
    cash sits in cash classes, when there is no cash figure, and when the
    payload carries no ``components``.
    """
    totals = report.get("totals")
    cash = totals.get("cash") if isinstance(totals, dict) else None
    components = cash.get("components") if isinstance(cash, dict) else None
    if not isinstance(components, list):
        return []
    out: list[dict[str, Any]] = []
    for component in components:
        if not isinstance(component, dict) or component.get("cash_class"):
            continue
        amount = to_decimal(component.get("amount"))
        if amount is None or amount == 0:
            continue
        accounts = component.get("accounts")
        out.append(
            {
                "main_class": component.get("main_class"),
                "amount": amount,
                "accounts": [
                    {
                        "account_no": str(account.get("account_no")),
                        "name": str(account.get("name")),
                        "amount": to_decimal(account.get("amount")),
                    }
                    for account in (accounts if isinstance(accounts, list) else [])
                    if isinstance(account, dict)
                ],
            }
        )
    return out


def fmt_cash_reconciliation(report: dict, currency: str = "USD", dp: int = 0) -> list[str]:
    """:func:`bs_cash_reconciliation` as lines to print beside the cash figure.

    "of which $22,501 presented under Other receivables", or "of which $7,000
    presented on no Balance Sheet row".
    """
    lines: list[str] = []
    for part in bs_cash_reconciliation(report):
        where = (
            "on no Balance Sheet row"
            if part["main_class"] is None
            else f"under {part['main_class']}"
        )
        lines.append(f"of which {fmt(part['amount'], currency, dp)} presented {where}")
    return lines


# Which side of the bottom line a P&L band sits on. CLOSED vocabulary — the
# seven bands declared in ``seed/canonical_statement_map.json`` — so this is a
# lookup, not a heuristic, and an unknown key falls through to "I can't tell"
# rather than to a default.
_EXPENSE_BANDS: frozenset[str] = frozenset(
    {
        "cost_of_sales",
        "operating_expenses",
        "finance_expenses_income",
        "other_expenses_income",
        "tax_expenses",
    }
)
_INCOME_BANDS: frozenset[str] = frozenset({"revenues", "equity_in_earnings_of_subsidiary"})

# Computed rows carry a ``role`` instead of a band.
_EXPENSE_ROLES: frozenset[str] = frozenset(
    {"total_opex", "total_expenses", "taxes", "depreciation", "tax_note_subtotal"}
)
_INCOME_ROLES: frozenset[str] = frozenset(
    {
        "gross_margin",
        "pct_gross_margin",
        "operating_income",
        "income_before_tax",
        "net_profit",
        "adjusted_net_profit",
        "ebitda",
    }
)


def expense_polarity(report: dict) -> dict[Any, bool]:
    """Map ``row_num`` → is-this-an-expense, for the rows that can be resolved.

    A row ABSENT from the returned map is one whose side of the bottom line
    could not be determined. That is deliberate and load-bearing: the caller
    must then decline to render a favourable/unfavourable verdict, because
    guessing the side of a variance INVERTS it — "spent $80k more than plan"
    reads as good news. A default here would be a wrong answer wearing the
    costume of a right one.

    This replaces a set of pinned row numbers (``{6, 10, 11, 12, 13, ...}``)
    plus two pinned note RANGES. The ranges were the worse half: a band that
    widens slides real expense rows out of the range and revenue rows into it,
    so two rows swap verdicts at once and the report still looks well-formed.

    Note-detail leaves inherit from the headline row they back, via
    ``parent_row_num``. That is a coordinate, but a legitimate one — it is read
    out of the very payload being classified, so it never outlives its frame.
    """
    rows = report.get("rows", [])
    by_row: dict[Any, dict] = {r.get("row_num"): r for r in rows if r.get("row_num") is not None}

    def _own(row: dict) -> bool | None:
        band = row.get("band_key")
        if band in _EXPENSE_BANDS:
            return True
        if band in _INCOME_BANDS:
            return False
        role = row.get("role")
        if role in _EXPENSE_ROLES:
            return True
        if role in _INCOME_ROLES:
            return False
        heading = row.get("heading_key")
        if heading in _EXPENSE_BANDS:
            return True
        if heading in _INCOME_BANDS:
            return False
        return None

    out: dict[Any, bool] = {}
    for row in rows:
        row_num = row.get("row_num")
        if row_num is None:
            continue
        polarity = _own(row)
        if polarity is None:
            # A note leaf carries no band of its own; inherit from its parent.
            parent = by_row.get(row.get("parent_row_num"))
            if parent is not None:
                polarity = _own(parent)
        if polarity is not None:
            out[row_num] = polarity
    return out


def fmt_figure(figure: Figure, currency: str = "USD", dp: int = 0) -> str:
    """Render a :class:`Figure` — including, explicitly, the case it could not resolve.

    "not identified" and "—" say different things and must not collapse into
    each other: the first is "I could not find this line", the second is "the
    line is there and the period is empty". Neither is ``0``.
    """
    if not figure.resolved:
        return "not identified"
    return fmt(figure.value, currency, dp)


# Row types that aggregate other rows or carry no journal lines of their own,
# so `drilldown` on them is wasted (it returns nothing and `sum_matches_cell`
# is false). `is_subtotal` already covers subtotal/net_section/grand_total; the
# rest are headers, balance anchors, and formula/reference rows.
_NON_DRILLABLE_ROW_TYPES: frozenset[str] = frozenset(
    {
        "header",
        "subtotal",
        "net_section",
        "grand_total",
        "opening_cash",
        "closing_cash",
        "check",
        "other_formula",
        "unclassified",
    }
)


def is_drillable(row: dict, column: str = "amount") -> bool:
    """Is this report row worth a ``drilldown`` call?

    ``drilldown`` fetches the journal lines under a **leaf cell**. It is wasted on
    two kinds of rows — exactly the ones that produced the screen full of empty
    results:

    * **Aggregators** — subtotal / net-section / grand-total / header / check /
      balance-anchor rows. They sum *other* rows, so they have no lines of their
      own (``sum_matches_cell`` comes back false). To understand one, read its
      child detail rows or call ``explain`` (which shows the formula + children),
      not ``drilldown``.
    * **Zero / no-data cells** — there are no lines to fetch, so the call returns
      an empty sample.

    Screen with this before drilling so you only spend calls on cells that
    actually have transactions behind them.
    """
    if row.get("is_subtotal"):
        return False
    if row.get("row_type") in _NON_DRILLABLE_ROW_TYPES:
        return False
    value = _row_amount(row, column)
    return value is not None and value != 0


def drillable_rows(
    report: dict,
    *,
    column: str = "amount",
    section: str | None = None,
    top: int | None = None,
) -> list[dict[str, Any]]:
    """The detail rows worth drilling, **largest absolute value first**.

    This is the list to iterate when you must trace several cells: it drops the
    aggregators and the zero/no-data cells (see :func:`is_drillable`) and ranks
    what remains by materiality, so you drill the cells that move the number and
    skip the noise. Cap with ``top`` to stay to the material few.
    """
    out: list[dict[str, Any]] = []
    for row in report.get("rows", []):
        if section is not None and row.get("section") != section:
            continue
        if not is_drillable(row, column):
            continue
        out.append(
            {
                "row": row.get("row_num"),
                "label": row.get("label"),
                "section": row.get("section"),
                "value": _row_amount(row, column),
            }
        )
    out.sort(key=lambda r: abs(r["value"]), reverse=True)
    return out[:top] if top else out


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
                # Relayed so a caller can resolve the row's SIDE of the bottom
                # line by identity (see :func:`expense_polarity`) instead of by
                # its position. Dropping them here is what forced the caller to
                # pin row numbers in the first place.
                "role": row.get("role"),
                "heading_key": row.get("heading_key"),
                "band_key": row.get("band_key"),
                "parent_row_num": row.get("parent_row_num"),
            }
        )
    rows.sort(key=lambda r: abs(r["variance"]), reverse=True)
    return rows[:top] if top else rows


def tieout_status(report: dict) -> dict[str, Any]:
    """Summarize whatever reconciliation check a report carries.

    A CFO assistant should never present numbers without confirming the books
    tie out. Different reports expose the check differently; this normalizes them
    to ``{ok: bool|None, delta: Decimal|None, kind: str, unresolved: list[str]}``.

    ``ok`` has THREE answers, and the third one is the point:

    * ``True``  — the check ran and the delta is zero.
    * ``False`` — the check ran and the books are off. Say so prominently.
    * ``None``  — the check could **not be evaluated**, or the report carries
      none at all. Never present this as a pass.

    EVERY report that publishes a delta also publishes why it might not be a
    measurement, and this function reads BOTH names because the backend uses
    two:

    * The P&L / BVA envelopes carry ``check_delta`` beside ``check_unresolved``.
      When an operand cannot be resolved (no ``net_profit`` role row, no P&L
      routing, a routed ``main_class`` that reached no band) the backend
      publishes ``0`` as a PLACEHOLDER and lists the reasons there.
    * The Balance Sheet / Trial Balance / consolidated envelopes carry
      ``balance_check_delta`` beside ``balance_check_unresolved_roles`` — the
      SAME contract under a different name. When a grand-total role cannot be
      resolved the missing role defaults to 0, the delta is a placeholder, and
      that field's own comment says no consumer may present it as one.

    Reading either ``0`` alone reports a clean tie-out over a control that
    never ran — the false green these fields exist to prevent. So a non-empty
    list under EITHER name returns ``ok: None`` with the reasons attached, and
    the caller must say "not evaluated, and here is why". Matching only one of
    the two names is worse than matching neither: ``balance_check_delta`` is
    tried FIRST, so a Balance Sheet with unresolved roles would come back
    ``ok: True`` — a green tie-out on the one report where the backend already
    ships the signal.

    **``unresolved_roles`` is a THIRD name, and it refuses the tie-out outright**
    It is not another reason the DELTA is a placeholder —
    it says which computed SUBTOTALS the group's template stamps on no row, so
    Gross margin / Operating income / EBITDA / Net profit are published as
    structural zeros with a real, zero ``check_delta`` beside them. Every other
    channel already says so: the screen shows a notice strip, both xlsx sheets
    write the sentence on the disclosure row, and the consolidated report
    publishes a ``fail``. Without this branch the assistant was the one channel
    left quieter than the screen about the same wire — it would answer "the
    books tie out" and then quote a fabricated Net Profit, which is the exact
    combination (``check_delta == 0`` AND a fabricated headline) that makes this
    worth reading. ``ok: False``, not ``None``: the backend NAMED a defect, so
    this is a finding, not a failure to look.

    The MCP tool docstring warns the model about the same field. That warning
    stays, and it is no longer the only mitigation — a prompt is guidance, not a
    guarantee, and a deterministic refusal is what makes the guidance
    unnecessary.
    """
    totals = report.get("totals", {})
    # Checked BEFORE the delta names, and on its own: it is the one signal that
    # is true regardless of which delta the report carries, and a report can
    # publish a perfectly zero delta while its headlines are fabrications.
    unresolved_roles = [str(r) for r in (totals.get("unresolved_roles") or [])]
    for key in ("balance_check_delta", "check_delta"):
        if key in totals:
            d = to_decimal(totals[key])
            unresolved = [
                str(r)
                for name in ("check_unresolved", "balance_check_unresolved_roles")
                for r in (totals.get(name) or [])
            ]
            if unresolved_roles:
                return {
                    "ok": False,
                    "delta": d,
                    "kind": key,
                    "unresolved": unresolved,
                    "unresolved_roles": unresolved_roles,
                    "reason": (
                        "computed subtotals are stamped on no row and print as structural "
                        f"zeros: {', '.join(unresolved_roles)}. The tie-out delta is real "
                        "but the headline figures it reconciles are not measurements. "
                        "Re-provision the group's templates (Settings → Statement routing)."
                    ),
                }
            if unresolved:
                return {"ok": None, "delta": d, "kind": key, "unresolved": unresolved}
            return {"ok": d == 0, "delta": d, "kind": key, "unresolved": []}
    if "tieout" in report:
        d = to_decimal(report["tieout"].get("period_delta"))
        return {"ok": d == 0, "delta": d, "kind": "cf_period_delta", "unresolved": []}
    if "tie_out_ok" in report:
        return {
            "ok": bool(report["tie_out_ok"]),
            "delta": None,
            "kind": "tie_out_ok",
            "unresolved": [],
        }
    return {"ok": None, "delta": None, "kind": "none", "unresolved": []}


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

    p_drill = sub.add_parser(
        "drillable", help="rows worth a drilldown (detail + non-zero), by |value|"
    )
    p_drill.add_argument("file")
    p_drill.add_argument("--section")
    p_drill.add_argument("--column", default="amount")
    p_drill.add_argument("--top", type=int)

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
        unresolved = status.get("unresolved") or []
        flag = {True: "OK", False: "OFF", None: "NOT EVALUATED" if unresolved else "n/a"}[
            status["ok"]
        ]
        print(f"{'tie-out':>28}: {flag}  (delta {fmt(status['delta'])}, {status['kind']})")
        for reason in unresolved:
            print(f"{'':>28}  ! {reason}")
    elif args.cmd == "kpis":
        for k in kpi_view(report):
            print(f"  {k['label']:>14}: {k['value']:>16}   ({k['comparator']})")
    elif args.cmd == "drillable":
        rows = drillable_rows(
            report, column=args.column, section=args.section, top=args.top
        )
        if not rows:
            print("  (no drillable cells — all aggregators or zero/no-data)")
        for r in rows:
            print(f"  [{r['row']:>4}] {fmt(r['value']):>16}  {r['label']}")
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
