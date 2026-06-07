---
name: lucid-platform-guide
description: >-
  Foundational guide for reading financial data from the Lucid MCP connector
  (the read-only Lucid CFO platform: trial balance, balance sheet, P&L, cash
  flow, budget-vs-actual, dashboard, plus explain/drilldown). Use this WHENEVER
  a task involves pulling numbers from Lucid — company financials, monthly
  reports, KPIs, "how did we do", revenue/margin/cash/runway/burn questions,
  or any request that should hit the Lucid tools. It teaches the non-obvious
  mechanics every other Lucid skill depends on: resolving company entities,
  the period grammar (2025-03, FY2025, YTD@..., R12@...), view modes
  (base/aje/lucid), the money envelope, comparison gating, mandatory tie-out
  checks, and how to handle the large report payloads without blowing up
  context. Read this first; the workflow skills build on it.
---

# Driving the Lucid financial-data platform

Lucid is a CFO analytics platform built on **journal-entry lines** as the atomic
unit. The MCP connector exposes it **read-only** and **RLS-scoped** — every call
forwards the caller's token and the backend returns only the companies and
periods they're authorized to see. Your job is to use these tools the way a sharp
controller would: resolve the right entity, pick the right period and view, pull
compactly, **prove the books tie out**, then analyze.

## The tools

**Entity resolution** (do this first — report tools need a real company handle):
- `list_entities()` → every company you can access: `{code, name, is_root, currency}`.
- `search_entities(query)` → closest matches to a name/code. Pass a result's
  `code` as the `company` argument everywhere else. `is_root` marks a parent /
  consolidation entity vs a subsidiary.

**Reports** (all take `company`, `period`, `view`, and the comparison/extra args below):
- `get_dashboard` — CFO home bundle: 4 KPIs (cash, runway, revenue QTD, gross
  margin) + an OpEx donut + a tie-out flag.
- `get_pl` — Profit & Loss (income statement): revenue, margins, OpEx, EBITDA.
- `get_balance_sheet` — point-in-time assets / liabilities / equity.
- `get_trial_balance` — account-level debit/credit/balance.
- `get_cash_flow_direct` — direct-method cash flow + a bank reconciliation banner.
- `get_bva` — Budget vs Actual: a P&L with `actual` / `budget` / `variance` per row.

**Cell introspection** (answer "why is this number what it is"):
- `explain(report, period, row, column)` — the full derivation of one cell.
- `drilldown(report, period, row, column, ...)` — the journal lines under a cell.

## The golden path

1. **Resolve the company.** Never guess a handle. `search_entities` (or
   `list_entities`) → use the exact `code`. If the user names "the US sub" or a
   parent, resolve it explicitly; an unknown handle returns a clean error, not data.
2. **Pick the period and view deliberately** (see below). When unsure of the view,
   default to `lucid` and say so.
3. **Pull compactly.** Reports are large — request a single period and the section
   you need; don't add `compare` / `include_trend` / `include_composition` unless
   the question requires them (see *Payload size*).
4. **Check the tie-out before you trust a number** (see *Tie-out discipline*).
5. **Analyze with the shared helper** so every skill parses money the same way.

## Period grammar

`period` is a single string. The vocabulary:

| Form | Meaning | Example |
|---|---|---|
| `YYYY-MM` | one month | `2025-03` |
| `YYYY-Qn` | one quarter | `2025-Q1` |
| `YYYY-Hn` | one half | `2025-H1` |
| `FYYYYY` | full fiscal year | `FY2025` |
| `YTD@YYYY-MM` | year-to-date through a month | `YTD@2025-03` |
| `R12@YYYY-MM` | rolling 12 months ending a month | `R12@2025-03` |
| `custom:START..END` | arbitrary window (ISO dates) | `custom:2025-01-01..2025-03-31` |

P&L / cash flow / BVA are **flows** — to cover several months use a wider period
(`FY2025`, `2025-Q1`), don't sum single months yourself. Balance sheet / trial
balance are **snapshots** — they report the position as of the period end.

## View modes

The `view` selects which ledger layers are included. The numbers differ
materially between views, so state which one you used.

| Report | Views | Default `lucid` means |
|---|---|---|
| `get_trial_balance` | `erp_only`, `lucid` | ERP ledger **+** approved Controller-Layer (adjusting) entries |
| all others | `base`, `aje`, `lucid` | `base` (ERP) **+** `aje` (adjusting overlay) |

- `base` / `erp_only` — the raw books from the source accounting system.
- `aje` — the Controller-Layer adjustments **only** (the value Lucid adds at close).
- `lucid` — the adjusted, close-ready numbers. **This is the default and what a
  CFO usually wants.** Use `base` vs `lucid` to show the impact of adjustments.

## The money envelope — never divide by 100

Every monetary field arrives already formatted in **major units** (dollars):

```json
{"amount": "1234567.89", "currency": "USD", "units": "major"}
```

`amount` is an exact decimal **string**. Read it as dollars as-is. Do **not**
multiply or divide by 100 — that's a frequent and embarrassing error. Some fields
are plain numbers instead (counts; the dashboard's `months` and `bps` units;
ratios) and some are `null` (genuine "no data" — not zero). The shared helper
(below) handles all of these; prefer it over hand-parsing.

## Comparisons (multi-period)

Two ways to get more than one column:

- **`compare`** — a shortcut: `"mom"` | `"qoq"` | `"yoy"`. Expands to a 5-period
  trailing series per row. **It is gated by the primary period kind** — invalid
  pairs return a 400:

  | primary kind | mom | qoq | yoy |
  |---|---|---|---|
  | month | ✅ | ✅ | ✅ |
  | quarter | ❌ | ✅ | ✅ |
  | half / ytd / fy / range | ❌ | ❌ | ✅ |

- **`periods="2025-01,2025-02,2025-03"`** — an explicit list (takes precedence
  over `compare`). Each row gets an aligned `series` in that order.

**Gotcha:** the per-row `series` array is **not labelled** with its column periods
in the payload. With `compare` you can't be sure which trailing periods you got —
so when the column identity matters, prefer explicit `periods=` (you control and
therefore know the order). `include_trend=true` adds a 12-element trailing-month
`trend` per row (ending at the primary period).

## Tie-out discipline

Lucid is built on the rule that classified lines must reconcile to the source
books. **Every report carries a reconciliation check — verify it before
presenting numbers**, the way a controller signs off a close:

| Report | Where the check lives | Tied out when |
|---|---|---|
| Trial balance | `totals.balance_check_delta` | `= 0` |
| Balance sheet | `totals.balance_check_delta` | `= 0` |
| P&L / BVA | `totals.check_delta` | `= 0` |
| Cash flow | `tieout.period_delta` (+ per-month `delta`) | `= 0` |
| Dashboard | `tie_out_ok` | `true` |

If a check is non-zero, **say so prominently** and treat the affected figures as
suspect — that's a books problem worth surfacing, not something to paper over.

## Payload size — reports are big, retrieve compactly

A full P&L is ~170 rows; with `compare` it can exceed the tool-result limit and
the harness **spills it to a file**, returning a path instead of the JSON. This is
normal. To stay efficient:

- Ask for **one period** and only what you need. Avoid `compare` /
  `include_trend` / `include_composition` unless the question demands them.
- The reports carry both detail and subtotal rows; the **headline figures live in
  `totals`** and in the subtotal rows — you rarely need every leaf line.
- When a result spills to a file, **don't read the raw JSON back into context.**
  Use the shared helper or `jq` to pull just what you need:

  ```bash
  python ${CLAUDE_PLUGIN_ROOT}/scripts/lucid_utils.py totals <spfilled.json>
  python ${CLAUDE_PLUGIN_ROOT}/scripts/lucid_utils.py rows <spilled.json> --section summary --nonzero
  jq '.totals' <spilled.json>
  ```

## The shared helper

`${CLAUDE_PLUGIN_ROOT}/scripts/lucid_utils.py` is the one place money parsing,
ratios, and table-shaping live, so numbers never disagree between skills. Import
it in analysis scripts:

```python
import sys; sys.path.insert(0, f"{PLUGIN_ROOT}/scripts")
from lucid_utils import to_decimal, fmt, report_rows, find_row, pct, \
    variance_table, kpi_view, tieout_status, growth, runway_months
```

Key functions: `to_decimal(field)` (envelope/number/null → `Decimal|None`),
`fmt(value)` ($-formatted), `report_rows(report, section=…, nonzero=…)`,
`find_row(report, row_num)`, `pct(a, b)`, `kpi_view(dashboard)` (unit-aware),
`variance_table(bva)`, `tieout_status(report)`. Or run it as a CLI (see above).

## Report row maps & exact response shapes

The report templates use **stable row numbers** (e.g. P&L row 24 = Net Profit) —
essential for `explain` / `drilldown` and for reading subtotals. The full row maps
for every report, plus the exact JSON shape of each tool's response, are in:

→ **`reference/report-reference.md`** — read it when you need a specific row
number, section name, or the field layout of a response.

## Which workflow skill to reach for

| The user wants… | Skill |
|---|---|
| "How are we doing", monthly close snapshot | `lucid:financial-position-review` |
| Revenue, gross margin, OpEx, profitability trends | `lucid:pl-and-margin-analysis` |
| Cash, burn, runway, what's draining cash | `lucid:cash-and-runway` |
| Where are we vs budget, variance drivers | `lucid:budget-vs-actual` |
| Liquidity, working capital, AR/AP, equity | `lucid:balance-sheet-review` |
| "Why is this number this", trace to journal lines | `lucid:explain-and-audit` |
| A board-ready pack / export | `lucid:board-pack` |
