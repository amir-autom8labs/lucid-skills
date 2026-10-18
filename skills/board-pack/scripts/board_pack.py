#!/usr/bin/env python3
"""Assemble a board-pack dataset from the five Lucid report payloads.

This is the orchestration glue for the ``lucid:board-pack`` skill. It reads the
already-pulled Lucid payloads — dashboard, P&L, balance sheet, cash flow, and
budget-vs-actual (each a tool result, possibly spilled to a file) — and emits ONE
tidy, labelled, multi-sheet dataset for a document skill (pdf / pptx) to
render. It also runs the cross-statement **reconciliation** that is the whole
point of a board pack: the same cash everywhere, the same net result everywhere,
every tie-out green.

It deliberately does NOT call Lucid, fetch anything, or render documents. Pull
the reports with the MCP tools first (one company + period + view, in one pass),
then feed the payloads here. All money parsing, the dashboard unit handling, the
balance-sheet sign-flip, and the variance ranking come from the shared
``lucid_utils`` helper so the numbers match every other Lucid skill exactly.

Usage::

    python board_pack.py --dashboard d.json --pl pl.json --bs bs.json \
        --cf cf.json --bva bva.json --format json   # or csv

Any input may be omitted; the corresponding sheets are simply skipped. Output
goes to stdout (JSON bundle) or, for ``--format csv``, one ``board_pack_<sheet>.csv``
per sheet in ``--outdir`` (default: current directory). Stdlib only + lucid_utils.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from decimal import Decimal
from typing import Any

# Self-contained: this skill bundles lucid_utils.py beside this script. Prepend
# this script's own dir so `from lucid_utils import ...` resolves to the sibling
# copy in any runtime (Claude Code, Managed Agents, claude.ai) — the whole skill
# dir, scripts included, is uploaded together, so no absolute plugin path is needed.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lucid_utils import (  # noqa: E402
    Figure,
    bs_cash,
    bs_cash_disclosures,
    currency_of,
    fmt,
    fmt_cash_reconciliation,
    fmt_figure,
    kpi_view,
    load_json,
    report_rows,
    role_figure,
    role_projected,
    tieout_status,
    to_decimal,
    total_figure,
    variance_table,
)

# This block used to hold ten pinned template rows — ``BS_CASH = 5``,
# ``PL_NET_PROFIT = 24``, ... — all read off one reference chart and correct only there.
# A board pack is the worst place for them: it is the document a board acts on,
# and prose has no footing check, so "Cash & equivalents" stating trade debtors
# reaches a boardroom looking exactly like cash.
#
# Two of the ten were also simply DEAD: ``CF_CLOSING_CASH = 44`` and
# ``CF_OPENING_CASH = 43`` were never read — this file already takes both from
# ``cf.totals.closing_cash_end`` / ``opening_cash_start``, which is the correct
# identity-bound source. They are deleted rather than converted.

# The rows a board pack shows that CANNOT be identified on the wire: a BS leaf
# is named only by the tenant's own ``main_class`` vocabulary, and nothing says
# which of a tenant's mains means "cash" or "accounts receivable". Declined
# rather than guessed — see the long note in ``balance-sheet-review``.
_NO_SEMANTIC_IDENTITY = (
    "the wire carries no semantic identity for this line — a BS leaf is named "
    "only by the tenant's own main_class vocabulary"
)


def _declined(line: str) -> Figure:
    """A leaf this pack cannot identify — reported as such, never as 0."""
    return Figure(unresolved_reason=f"{line}: {_NO_SEMANTIC_IDENTITY}")


def _prefer_total(report: dict, total_key: str, role: str) -> Figure:
    """A headline figure from ``totals`` if present, else from the row's ``role``."""
    figure = total_figure(report, total_key)
    return figure if figure.resolved else role_figure(report, role)


def _num(value: Decimal | None) -> float | None:
    """Decimal → float for JSON/CSV (None passes through)."""
    return None if value is None else float(value)


def _abs(value: Decimal | None) -> Decimal | None:
    return None if value is None else abs(value)


def _tie(report: dict | None) -> dict[str, Any]:
    if report is None:
        return {"present": False}
    status = tieout_status(report)
    return {
        "present": True,
        # THREE-valued: True / False / None, where None means the control could
        # not be evaluated (``unresolved`` says why) or the report carries no
        # check at all. Never collapse None to a pass when reporting.
        "ok": status["ok"],
        "delta": _num(status["delta"]),
        "kind": status["kind"],
        "unresolved": status.get("unresolved") or [],
    }


# --------------------------------------------------------------------------- #
# Per-exhibit sheets
# --------------------------------------------------------------------------- #
def kpi_sheet(dashboard: dict) -> list[dict[str, Any]]:
    """KPI scorecard — unit-aware (cash $, runway mo, gross margin %)."""
    return [
        {"kpi": k["label"], "value": k["value"], "vs_prior": k["comparator"]}
        for k in kpi_view(dashboard)
    ]


def pl_sheet(pl: dict) -> list[dict[str, Any]]:
    """P&L headline rows (the board view). Notes are left out on purpose.

    ``get_pl`` does not return % Gross Margin, Adjusted Net Profit, Total
    expenses or Depreciation, so this sheet has no such lines. A row the backend
    marks ``uncomputed`` keeps its label and gets no figure — ``report_rows``
    hands it over with ``value: None``, so it renders as "—" here like any other
    absent figure.

    ``projected`` is the part of a line's amount that is projected (an estimate
    of entries not booked yet, in an open month), ``None`` when there is none;
    ``disclosures`` states it in words, so the CSV carries it into the deck.
    """
    out: list[dict[str, Any]] = []
    for r in report_rows(pl, section="summary"):
        projected = r.get("projected")
        out.append(
            {
                "row": r["row"],
                "line": r["label"],
                "amount": _num(r["value"]),
                "display": fmt(r["value"]),
                "is_subtotal": r["is_subtotal"],
                "projected": _num(projected),
                "disclosures": (
                    f"of which {fmt(projected)} projected (not booked yet)" if projected else ""
                ),
            }
        )
    return out


def bs_sheet(bs: dict) -> list[dict[str, Any]]:
    """Balance sheet, sign-flipped to positive magnitudes for human reading."""
    cur = currency_of(None)
    rows: list[dict[str, Any]] = []
    # Assets stay positive; liabilities & equity flip to magnitudes.
    # Disclosures and the reconciliation ride on the SHEET row, not only in the
    # reconciliation block. `--format csv` writes the sheet to
    # board_pack_balance_sheet.csv and the reconciliation to a separate JSON,
    # and the CSV is what goes in the deck — so a note that lives only in
    # reconcile() never reaches the boardroom. Cash presented under another
    # class is part of "Cash & equivalents" here and of that class's own line
    # on the statement; the note is what tells the reader so.
    cash_disclosures = bs_cash_disclosures(bs)
    cash_reconciliation = fmt_cash_reconciliation(bs, cur)
    # Projected entries reach the balance sheet through the *Projected
    # accruals* liability and the current-year result in equity; the backend
    # foots each subtotal's projected part, read here from the role's row.
    projected_by_label: dict[str, Decimal | None] = {
        "Total current liabilities": role_projected(bs, "total_current_liabilities"),
        "Total equity": role_projected(bs, "total_equity"),
    }
    spec: list[tuple[str, Figure, bool]] = [
        ("Cash & equivalents", bs_cash(bs), False),
        ("Accounts receivable", _declined("Accounts receivable"), False),
        ("Total current assets", role_figure(bs, "total_current_assets"), False),
        ("TOTAL ASSETS", _prefer_total(bs, "total_assets", "total_assets"), False),
        ("Accounts payable", _declined("Accounts payable"), True),
        ("Total current liabilities", role_figure(bs, "total_current_liabilities"), True),
        (
            "Total long-term liabilities",
            role_figure(bs, "total_long_term_liabilities"),
            True,
        ),
        ("Total equity", _prefer_total(bs, "total_equity", "total_equity"), True),
    ]
    for label, figure, flip in spec:
        disp_val = _abs(figure.value) if flip else figure.value
        disp = Figure(value=disp_val, unresolved_reason=figure.unresolved_reason)
        projected = projected_by_label.get(label)
        disclosures = list(cash_disclosures) if label.startswith("Cash") else []
        if projected:
            # Same sign as the line: projections make up part of it; opposite
            # sign: they reduce it (a projected expense lowers equity).
            same = figure.value is None or (projected < 0) == (figure.value < 0)
            verb = "includes" if same else "lowered by"
            disclosures.append(
                f"{verb} {fmt(_abs(projected), cur)} of projected entries (not booked yet)"
            )
        rows.append(
            {
                "line": label,
                # ``amount`` stays None when the line could not be identified —
                # NOT 0. A machine-readable 0 here is a figure a downstream
                # renderer would total, and "I could not find this line" must
                # never foot into anything.
                "amount": _num(disp.value) if disp.resolved else None,
                "display": fmt_figure(disp, cur),
                "unresolved_reason": disp.unresolved_reason,
                # Emitted on every row so the CSV keeps one stable column set
                # (DictWriter takes its fieldnames from the first row) and so a
                # reader scanning the column sees it is normally blank.
                "disclosures": "; ".join(disclosures),
                # "of which $X presented under <class>" — same column rule.
                "reconciliation": (
                    "; ".join(cash_reconciliation) if label.startswith("Cash") else ""
                ),
            }
        )
    return rows


def cf_sheet(cf: dict) -> list[dict[str, Any]]:
    """Cash flow headline: the three section nets, total change, open/close."""
    totals = cf.get("totals", {})
    spec = [
        ("Net cash — operating", totals.get("net_operating")),
        ("Net cash — investing", totals.get("net_investing")),
        ("Net cash — financing", totals.get("net_financing")),
        ("Total increase/(decrease) in cash", totals.get("total_change")),
        ("Cash at beginning of period", totals.get("opening_cash_start")),
        ("Cash at end of period", totals.get("closing_cash_end")),
    ]
    rows: list[dict[str, Any]] = []
    for label, val in spec:
        d = to_decimal(val)
        rows.append({"line": label, "amount": _num(d), "display": fmt(d)})
    return rows


def bva_sheet(bva: dict, top: int = 10) -> list[dict[str, Any]]:
    """Top variances by magnitude (the 'where are we off plan' view)."""
    out: list[dict[str, Any]] = []
    for r in variance_table(bva, top=top):
        vp = r["variance_pct"]
        out.append(
            {
                "row": r["row"],
                "line": r["label"],
                "actual": _num(r["actual"]),
                "budget": _num(r["budget"]),
                "variance": _num(r["variance"]),
                "variance_pct": None if vp is None else round(float(vp) * 100, 1),
            }
        )
    return out


# --------------------------------------------------------------------------- #
# Cross-statement reconciliation — the point of the whole pack
# --------------------------------------------------------------------------- #
def reconcile(
    dashboard: dict | None,
    pl: dict | None,
    bs: dict | None,
    cf: dict | None,
) -> dict[str, Any]:
    """Prove the statements agree before anything is exported.

    Two value ties (cash everywhere; net result on P&L vs balance sheet) plus a
    roll-up of every report's own tie-out flag. Each check is OK / MISMATCH /
    n/a (when an input is missing).
    """
    checks: list[dict[str, Any]] = []

    # --- Cash: dashboard KPI == BS row 5 == CF closing_cash ---------------- #
    dash_cash = None
    if dashboard:
        for k in dashboard.get("kpis", []):
            if k.get("kind") == "cash":
                dash_cash = to_decimal(k.get("amount"))
                break
    # The Balance Sheet's own cash line is back in this check, but by IDENTITY.
    # It used to be keyed ``balance_sheet_row5`` — a name that stated the bug in
    # its own output — and on any chart whose routing did not put cash first it
    # compared the dashboard's cash against trade debtors, reporting a mismatch
    # (or, worse, a match) about two different things. It now comes from
    # ``totals.cash``: the balance of the is_cash_pool accounts, counted per
    # account wherever the statement presents them.
    cf_close = (
        to_decimal(cf.get("totals", {}).get("closing_cash_end")) if cf else None
    )
    bs_cash_figure = bs_cash(bs) if bs else Figure(unresolved_reason="balance sheet not pulled")
    cash_vals = {
        "dashboard": dash_cash,
        "balance_sheet": bs_cash_figure.value if bs_cash_figure.resolved else None,
        "cf_closing": cf_close,
    }
    present = [v for v in cash_vals.values() if v is not None]
    if len(present) >= 2:
        ok = all(v == present[0] for v in present)
    else:
        ok = None
    check: dict[str, Any] = {
        "check": "cash_consistency",
        "ok": ok,
        "values": {k: _num(v) for k, v in cash_vals.items()},
        "display": {k: fmt(v) for k, v in cash_vals.items()},
    }
    # An operand that could not be resolved is DISCLOSED, not dropped: a
    # two-way check silently standing in for a three-way one reads as stronger
    # evidence than it is.
    if not bs_cash_figure.resolved:
        check["not_evaluated"] = {"balance_sheet": bs_cash_figure.unresolved_reason}
    disclosures = bs_cash_disclosures(bs) if bs else []
    cash_reconciliation = fmt_cash_reconciliation(bs) if bs else []
    if disclosures:
        # Every clause travels with the check: cash presented outside a cash
        # class ("includes", with the amounts behind it) and a cash class's
        # accounts that are not cash ("excludes", which carries no amount).
        check["disclosures"] = {"balance_sheet": disclosures}
        check["reconciliation"] = {"balance_sheet": cash_reconciliation}
    checks.append(check)

    # --- Net result: P&L row 24 vs BS row 55 (current-year P&L) ------------ #
    # BS current-year P&L sits in equity with the opposite sign, so compare
    # magnitudes (and report both raw values for the reader to eyeball).
    # Both sides are identity-bound: the P&L's ``net_profit`` role (or its
    # ``totals`` twin) against the BS's ``pl_loss_profit`` role.
    pl_net = _prefer_total(pl, "net_profit", "net_profit") if pl else Figure(
        unresolved_reason="P&L not pulled"
    )
    bs_cy = role_figure(bs, "pl_loss_profit") if bs else Figure(
        unresolved_reason="balance sheet not pulled"
    )
    if pl_net.value is not None and bs_cy.value is not None:
        net_ok = abs(pl_net.value) == abs(bs_cy.value)
    else:
        net_ok = None
    checks.append(
        {
            "check": "net_result_consistency",
            "ok": net_ok,
            "note": "BS current-year P&L is sign-flipped in equity; magnitudes compared.",
            "values": {
                "pl_net_profit": _num(pl_net.value),
                "bs_current_year_pl": _num(bs_cy.value),
            },
            "display": {
                "pl_net_profit": fmt_figure(pl_net),
                "bs_current_year_pl": fmt_figure(bs_cy),
            },
        }
    )

    # --- Every report's own tie-out ---------------------------------------- #
    tieouts = {
        "dashboard": _tie(dashboard),
        "pl": _tie(pl),
        "balance_sheet": _tie(bs),
        "cash_flow": _tie(cf),
    }
    # THREE outcomes, and the third one is why ``_tie`` is three-valued.
    # ``ok is None`` used to mean only "this report carries no tie-out field",
    # which was fine to skip. It now ALSO means "the control ran and could not
    # be evaluated" — the backend published a placeholder delta because an
    # operand was unresolvable. Filtering those out of the conjunction would
    # ship a board pack asserting the statements reconcile over a control that
    # never ran, which is the false green this whole signal exists to stop.
    # A present check with reasons attached is NOT evidence of anything.
    unevaluated = [
        name
        for name, t in tieouts.items()
        if t.get("present") and t.get("ok") is None and t.get("unresolved")
    ]
    mismatched = [
        name for name, t in tieouts.items() if t.get("present") and t.get("ok") is False
    ]
    value_mismatch = any(c["ok"] is False for c in checks)

    # ``overall_ok`` is strictly boolean only when every present control
    # produced a reading. ``None`` says "nothing mismatched, but something was
    # not evaluated" — never collapsed to True.
    if mismatched or value_mismatch:
        overall: bool | None = False
    elif unevaluated:
        overall = None
    else:
        overall = True
    return {
        "overall_ok": overall,
        "unevaluated": unevaluated,
        "value_checks": checks,
        "tie_outs": tieouts,
    }


# --------------------------------------------------------------------------- #
# Bundle + output
# --------------------------------------------------------------------------- #
def build_bundle(
    dashboard: dict | None,
    pl: dict | None,
    bs: dict | None,
    cf: dict | None,
    bva: dict | None,
    bva_top: int,
) -> dict[str, Any]:
    # Carry the locked basis from whatever report we have.
    any_report = next((r for r in (dashboard, pl, bs, cf, bva) if r), {})
    meta = {
        "view": any_report.get("view"),
        "period": any_report.get("period"),
        "generated_at": any_report.get("generated_at"),
    }
    sheets: dict[str, Any] = {}
    if dashboard:
        sheets["KPIs"] = kpi_sheet(dashboard)
    if pl:
        sheets["P&L"] = pl_sheet(pl)
    if bs:
        sheets["Balance Sheet"] = bs_sheet(bs)
    if cf:
        sheets["Cash Flow"] = cf_sheet(cf)
    if bva:
        sheets["BvA"] = bva_sheet(bva, top=bva_top)
    return {
        "meta": meta,
        "reconciliation": reconcile(dashboard, pl, bs, cf),
        "sheets": sheets,
    }


def _write_csvs(bundle: dict[str, Any], outdir: str) -> list[str]:
    written: list[str] = []
    for name, rows in bundle["sheets"].items():
        if not rows:
            continue
        safe = name.lower().replace("&", "and").replace(" ", "_")
        path = os.path.join(outdir, f"board_pack_{safe}.csv")
        fieldnames = list(rows[0].keys())
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assemble a board-pack dataset from Lucid payloads.")
    parser.add_argument("--dashboard")
    parser.add_argument("--pl")
    parser.add_argument("--bs")
    parser.add_argument("--cf")
    parser.add_argument("--bva")
    parser.add_argument("--bva-top", type=int, default=10)
    parser.add_argument("--format", choices=("json", "csv"), default="json")
    parser.add_argument("--outdir", default=".")
    args = parser.parse_args(argv)

    if not any([args.dashboard, args.pl, args.bs, args.cf, args.bva]):
        parser.error("provide at least one of --dashboard/--pl/--bs/--cf/--bva")

    dashboard = load_json(args.dashboard) if args.dashboard else None
    pl = load_json(args.pl) if args.pl else None
    bs = load_json(args.bs) if args.bs else None
    cf = load_json(args.cf) if args.cf else None
    bva = load_json(args.bva) if args.bva else None

    bundle = build_bundle(dashboard, pl, bs, cf, bva, args.bva_top)

    if args.format == "json":
        json.dump(bundle, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        paths = _write_csvs(bundle, args.outdir)
        recon_path = os.path.join(args.outdir, "board_pack_reconciliation.json")
        with open(recon_path, "w", encoding="utf-8") as fh:
            json.dump({"meta": bundle["meta"], "reconciliation": bundle["reconciliation"]}, fh, indent=2)
        for p in paths + [recon_path]:
            print(p)

    # Make a failed reconciliation visible on stderr (do not fail the run — the
    # caller may legitimately want to export and flag the mismatch in Section 7).
    recon = bundle["reconciliation"]
    if recon["overall_ok"] is False:
        print("WARNING: cross-statement reconciliation has MISMATCHES — flag them in Section 7.", file=sys.stderr)
    elif recon["overall_ok"] is None:
        names = ", ".join(recon.get("unevaluated") or []) or "one or more"
        print(
            f"WARNING: cross-statement reconciliation NOT EVALUATED ({names}) — a control "
            "could not be evaluated, so this pack is not reconciled. Say so in Section 7; "
            "do not present it as tying out.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
