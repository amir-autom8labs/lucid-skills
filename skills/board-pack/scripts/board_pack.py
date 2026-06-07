#!/usr/bin/env python3
"""Assemble a board-pack dataset from the five Lucid report payloads.

This is the orchestration glue for the ``lucid:board-pack`` skill. It reads the
already-pulled Lucid payloads — dashboard, P&L, balance sheet, cash flow, and
budget-vs-actual (each a tool result, possibly spilled to a file) — and emits ONE
tidy, labelled, multi-sheet dataset for a document skill (xlsx / pdf / pptx) to
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

# Import the shared helper. ${CLAUDE_PLUGIN_ROOT}/scripts is the canonical home;
# fall back to the repo layout (three dirs up from this script) when local.
_PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT")
_CANDIDATES = [
    os.path.join(_PLUGIN_ROOT, "scripts") if _PLUGIN_ROOT else None,
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts"),
]
for _c in _CANDIDATES:
    if _c and os.path.isdir(_c):
        sys.path.insert(0, _c)
        break

from lucid_utils import (  # noqa: E402
    bps_to_pct,
    currency_of,
    find_row,
    fmt,
    kpi_view,
    load_json,
    report_rows,
    tieout_status,
    to_decimal,
    variance_table,
)

# Stable template rows used for the cross-statement reconciliation.
PL_NET_PROFIT = 24
BS_CASH = 5
BS_AR = 8
BS_TCA = 16
BS_TOTAL_ASSETS = 24
BS_AP = 29
BS_TCL = 35
BS_TLTL = 44
BS_TOTAL_EQUITY = 57
BS_CURRENT_YEAR_PL = 55
CF_CLOSING_CASH = 44
CF_OPENING_CASH = 43


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
        "ok": status["ok"],
        "delta": _num(status["delta"]),
        "kind": status["kind"],
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
    """P&L headline rows (the board view). Notes are left out on purpose."""
    out: list[dict[str, Any]] = []
    for r in report_rows(pl, section="summary"):
        out.append(
            {
                "row": r["row"],
                "line": r["label"],
                "amount": _num(r["value"]),
                "display": fmt(r["value"]),
                "is_subtotal": r["is_subtotal"],
            }
        )
    return out


def bs_sheet(bs: dict) -> list[dict[str, Any]]:
    """Balance sheet, sign-flipped to positive magnitudes for human reading."""
    cur = currency_of(None)
    rows: list[dict[str, Any]] = []
    # Assets stay positive; liabilities & equity flip to magnitudes.
    spec = [
        ("Cash & equivalents", BS_CASH, False),
        ("Accounts receivable", BS_AR, False),
        ("Total current assets", BS_TCA, False),
        ("TOTAL ASSETS", BS_TOTAL_ASSETS, False),
        ("Accounts payable", BS_AP, True),
        ("Total current liabilities", BS_TCL, True),
        ("Total long-term liabilities", BS_TLTL, True),
        ("Total equity", BS_TOTAL_EQUITY, True),
    ]
    for label, rn, flip in spec:
        raw = find_row(bs, rn)
        disp_val = _abs(raw) if flip else raw
        rows.append(
            {
                "line": label,
                "amount": _num(disp_val),
                "display": fmt(disp_val, cur),
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
    bs_cash = find_row(bs, BS_CASH) if bs else None
    cf_close = (
        to_decimal(cf.get("totals", {}).get("closing_cash_end")) if cf else None
    )
    cash_vals = {"dashboard": dash_cash, "balance_sheet_row5": bs_cash, "cf_closing": cf_close}
    present = [v for v in cash_vals.values() if v is not None]
    if len(present) >= 2:
        ok = all(v == present[0] for v in present)
    else:
        ok = None
    checks.append(
        {
            "check": "cash_consistency",
            "ok": ok,
            "values": {k: _num(v) for k, v in cash_vals.items()},
            "display": {k: fmt(v) for k, v in cash_vals.items()},
        }
    )

    # --- Net result: P&L row 24 vs BS row 55 (current-year P&L) ------------ #
    # BS current-year P&L sits in equity with the opposite sign, so compare
    # magnitudes (and report both raw values for the reader to eyeball).
    pl_net = find_row(pl, PL_NET_PROFIT) if pl else None
    bs_cy = find_row(bs, BS_CURRENT_YEAR_PL) if bs else None
    if pl_net is not None and bs_cy is not None:
        net_ok = abs(pl_net) == abs(bs_cy)
    else:
        net_ok = None
    checks.append(
        {
            "check": "net_result_consistency",
            "ok": net_ok,
            "note": "BS current-year P&L is sign-flipped in equity; magnitudes compared.",
            "values": {"pl_net_profit": _num(pl_net), "bs_current_year_pl": _num(bs_cy)},
            "display": {"pl_net_profit": fmt(pl_net), "bs_current_year_pl": fmt(bs_cy)},
        }
    )

    # --- Every report's own tie-out ---------------------------------------- #
    tieouts = {
        "dashboard": _tie(dashboard),
        "pl": _tie(pl),
        "balance_sheet": _tie(bs),
        "cash_flow": _tie(cf),
    }
    all_tied = all(
        t["ok"] for t in tieouts.values() if t.get("present") and t.get("ok") is not None
    )

    overall = all(
        c["ok"] for c in checks if c["ok"] is not None
    ) and all_tied
    return {
        "overall_ok": overall,
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
    if bundle["reconciliation"]["overall_ok"] is False:
        print("WARNING: cross-statement reconciliation has MISMATCHES — flag them in Section 7.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
