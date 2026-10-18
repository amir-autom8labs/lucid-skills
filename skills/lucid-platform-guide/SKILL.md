---
name: lucid-platform-guide
description: >-
  Foundational guide for reading financial data from the Lucid MCP connector
  (the read-only Lucid CFO platform: trial balance, balance sheet, P&L, cash
  flow, budget-vs-actual, consolidation, workspace status, accounts, plus
  explain/drilldown). Use this WHENEVER
  a task involves pulling numbers from Lucid — company financials, monthly
  reports, KPIs, "how did we do", revenue/margin/cash/runway/burn questions,
  or any request that should hit the Lucid tools. It teaches the non-obvious
  mechanics every other Lucid skill depends on: resolving company entities,
  the period grammar (2025-03, FY2025, YTD@..., R12@...), view modes
  (base/aje/lucid) and projected entries, the money envelope, comparison gating, mandatory tie-out
  checks, and how to handle the large report payloads without blowing up
  context. It also carries the answer rules (voice, quoting figures, derived
  figures, routing to the right workflow skill). Read this first; the workflow
  skills build on it.
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
- `get_pl` — Profit & Loss (income statement): revenue, margins, OpEx, EBITDA.
- `get_balance_sheet` — point-in-time assets / liabilities / equity.
- `get_trial_balance` — account-level debit/credit/balance.
- `get_cash_flow_direct` — direct-method cash flow + a bank reconciliation banner.
- `get_bva` — Budget vs Actual: a P&L with `actual` / `budget` / `variance` per row.
  **Temporarily unavailable** — the tool currently returns a "budget-vs-actual is
  not available yet" stub; relay that rather than presenting variance numbers.

**Cell introspection** (answer "why is this number what it is"):
- `explain(report, period, row, column)` — the full derivation of one cell.
- `drilldown(report, period, row, column, ...)` — the journal lines under a cell.

**Situational awareness** (answer "where do we stand / what's on the table"):
- `get_status` — the operational front door: what's **pending** / waiting on the user,
  **report health** across the statements, and **recent activity**. Reach for it first
  on a vague or session-opening ask ("what's on the table", "anything I should look at",
  "can we close?"). Ask for `sections=["kpis"]` and it also serves the **headline KPI
  strip** (cash · runway · revenue · gross margin · operating profit · net profit ·
  burn) and, with `"moved"`, the month's largest changes — the same backend-computed
  figures the CFO dashboard draws, quoted verbatim. Those two are **opt-in**, so a
  plain call does not carry them. It still does not *explain* a figure (that's the
  report tools / `explain` / `drilldown`) or teach the app (that's `get_help`); a
  finding it turns up is then investigated with those. → `lucid:workspace-status`.

**Consolidation** (a group of entities, `companies=[...]`):
- `get_consolidated_report` — consolidated TB / BS / P&L across group entities,
  optionally with intercompany eliminations.
- `get_consolidation_readiness` — does the intercompany column net to zero?
- `get_ic_elim_proposals` — intercompany eliminations Lucid proposes, awaiting approval.
- `explain_consolidated` / `drilldown_consolidated` — the consolidated-cell
  versions of `explain` / `drilldown`.
- `get_close_readiness` — what is blocking the close, per entity, for a period
  (authoritative for "can we close?").

**Accounts and data questions** (why something looks wrong → `lucid:investigate-data-issue`):
- `list_accounts` — look up accounts in the chart of accounts (metadata, not figures).
- `get_account` — one account: its labels, where it lands on each report, and why.
- `get_account_history` — recorded changes to one account: who changed what, when.
- `get_line_placement` — the accounts on one BS / P&L / TB line and the rule that placed each.
- `get_cash_composition` — cash split by account currency and by bank account.
- `get_open_items` — what Lucid already holds open: is this already flagged or acknowledged?
- `get_check_catalogue` — what a check / finding / warning means and where its data is fixed.
- `get_my_access` — which fix permissions the user holds in a company.
- `list_movement_types` — the ERP movement-type reference list for a company.

**Using the app** (how-to, not numbers → `lucid:product-help`):
- `get_help(area?)` — the Lucid product user manual: menu paths, flows,
  troubleshooting.

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
| `get_trial_balance` | `erp_only`, `lucid` | ERP ledger **+** approved Controller-Layer (adjusting) entries **+** projections in open months |
| `get_balance_sheet`, `get_pl` | `base`, `aje`, `lucid` | `base` (ERP) **+** `aje` (adjusting overlay) **+** projections in open months |
| all others | `base`, `aje`, `lucid` | `base` (ERP) **+** `aje` (adjusting overlay); never projections |

- `base` / `erp_only` — the raw books from the source accounting system. Never
  includes a projection.
- `aje` — the Controller-Layer adjustments **only** (the value Lucid adds at close).
- `lucid` — the adjusted numbers, plus Lucid's **projected entries** for the
  recurring P&L entries (payroll, rent, retainers, …) that have not been booked
  yet in an **open** month. **This is the default and what a CFO usually
  wants.** Use `base` vs `lucid` to show the impact of adjustments.

### Projected entries — always say how much is projected

In an open month Lucid fills the recurring P&L entries that have not arrived yet
with **projected entries** (an estimate from the last months' pattern, removed
once the booked lines of the same account reach 80% of it). They are part of
the default `lucid` figures of the trial balance, balance sheet and P&L, exactly
as the web app shows them, and of the consolidated report (which follows the
same `include_projections`; intercompany series are never projected, since
eliminations never see projections). A closed month never holds an active one.
The cash tools are always booked-only. Projections reach only the month after
the last month with data: with books through August read in mid-October,
September is projected and October is not.

- `get_trial_balance`, `get_balance_sheet`, `get_pl`, `get_consolidated_report`,
  `explain` and `drilldown` take `include_projections` (default `true`). Pass `false` for the
  **booked-only** figure ("what's actually in the books"). Only the `lucid` view
  includes projections.
- The `totals` block carries no projected split: before stating a total, read
  its headline row (`density="summary"`), which carries `projected`. With
  `periods` / `compare` / `include_trend`, `series_projected` / `trend_projected`
  give each column's projected part, index for index with `series` / `trend`.
- Every row or cell with a projected part carries `projected` (a money envelope,
  the projected part of that figure) and the label `basis: "projected"`. With
  `include_composition`, the split is `{je, aje, projected}` and
  `je + aje + projected` is the amount. `drilldown` returns projection lines as
  their own sample, `projected_lines`, and its tie-out is
  `je_total + aje_total + projected_total == cell`.
- **Disclosure is mandatory.** Whenever a figure you state has a non-zero
  `projected`, say how much of it is projected, in the same sentence:
  *"Operating expenses for October are $480k, of which $310k is projected."*
  Carry the label into anything built on that figure (a margin, a variance, a
  board line). A projection is an estimate, never a booked fact — the same rule
  as the dashboard's cash projection (`labelled: "projected"`).
- Read `projected`; never compute it by subtracting a booked-only pull from a
  `lucid` pull, and never re-add it.
- **Checks stay booked.** Close readiness, the statement checks and the data
  checks always run without projections: a projection never makes a check pass
  or fail. Do not argue a tie-out with a projected figure.
- **Memory:** never save a figure that includes a projected part as a fact. Save
  it with the label and the date (*"Oct opex $480k incl. $310k projected, as of
  Oct 16"*), or not at all.

## The money envelope — read it as dollars, never divide by 100

Every monetary field you receive is already shaped into **major units** (dollars):

```json
{"amount": "1234567.89", "currency": "USD", "units": "major"}
```

`amount` is an exact decimal **string** — read it as dollars as-is.

Not everything is a money envelope:
- **Counts / ids / ratios** are plain numbers (`variance_pct`, row counts, …).
- **`null`** means genuine "no data" — not zero. Keep the two distinct.
- **Dashboard KPIs are special.** Each KPI carries a sibling `unit` label. When
  `unit == "cents"` the `amount` is a money envelope (dollars). When `unit` is
  `"months"` or `"bps"` the `amount` is a **bare integer** — months as-is, bps as
  basis-points×100 (`-2000` = −20.00%, ÷100 for percent). The `delta` fields are
  tagged the same way via `delta_unit`. Never read a `bps`/`months` value as dollars.

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
| P&L | `totals.check_delta` | `= 0` **and** `totals.check_unresolved` empty |
| BVA | `totals.check_delta` | `= 0` |
| Cash flow | `tieout.period_delta` (+ per-month `delta`) | `= 0` |
| Dashboard | `tie_out_ok` | `true` |

If a check is non-zero, **say so prominently** and treat the affected figures as
suspect — that's a books problem worth surfacing, not something to paper over.
A check that could not be EVALUATED is a third answer, distinct from both: the P&L's
`totals.check_unresolved` (a non-empty list of reasons) means its `0` is a placeholder.
Report it as "not evaluated, and here is why" — never as a pass.

## Payload size — reports are big, retrieve compactly

A full P&L is ~170 rows; with `compare` it can be large. How an oversized result
is handled is runtime-specific (Claude Code may **spill it to a file** and return
a path; other runtimes truncate or summarize). Either way, stay compact:

- **Fetch the summary density by default.** It returns just the ~25
  category-subtotal rows (each still carrying its `row_num`, `label`, `amount`,
  `series`) — a small payload that fits inline, no spill. Fetch a detailed density
  (or drill a single `section`) only when you need a line's leaf composition; the
  exact density vocabulary each report accepts lives on that tool's own schema.
  **The request `section` param is a fixed, closed
  set of drill blocks per report** — pass one of that report's blocks (P&L / BVA:
  `revenue | cogs | opex | finance | other`, where `opex` covers R&D / S&M / G&A;
  balance sheet: `assets | liabilities | equity`; cash flow:
  `operating | investing | financing`; trial balance has no `section`). It returns
  that block's rows plus their leaves; the enum lives on each tool's own schema, so
  you never guess a value. (Don't confuse it with the response `row.section` field,
  which is richer and per-report — see `reference/report-reference.md`.) A summary
  pull answers most questions and keeps every figure addressable by `row_num`.
- Ask for **one period** and only what you need. Avoid `compare` /
  `include_trend` / `include_composition` unless the question demands them.
- The **headline figures live in `totals`** (stable keys) and in the subtotal
  rows — you rarely need every leaf line. Read `totals` first.
- In a code-execution runtime, **don't read a huge raw JSON back into context** —
  extract just what you need with an analysis skill's bundled helper (run by its
  relative path, `scripts/lucid_utils.py`, from that skill's own dir) or `jq`:

  ```bash
  python scripts/lucid_utils.py totals report.json
  python scripts/lucid_utils.py rows   report.json --section summary --nonzero
  jq '.totals' report.json
  ```

## The helper is optional — parse inline when you can't run code

Each analysis skill **bundles `scripts/lucid_utils.py` in its own directory** so
it's self-contained: one tested place for money parsing, ratios, and table
shaping, so numbers never disagree between skills. In a code-execution runtime
(Claude Code, cowork) run it by its **relative path from the skill directory**
(`scripts/lucid_utils.py` — the whole skill dir, scripts included, is uploaded, so
relative paths resolve) or import it (the bundled scripts add their own directory
to `sys.path`, so `from lucid_utils import …` resolves to the sibling copy). Key
functions:
`to_decimal`, `fmt`, `report_rows`, `find_row`, `pct`, `kpi_view`,
`variance_table`, `tieout_status`, `growth`, `runway_months`; CLI subcommands
`rows` / `totals` / `kpis` / `bva`.

**But the helper is an optimization, not a requirement.** If you have no code tool
(e.g. on claude.ai in a pure-reasoning chat), just read the JSON directly — it's
simple:

- **Money field** → take `.amount` and read it as a dollar decimal — unless the
  row carries `uncomputed: true`, which says the backend computed no figure for
  it. Then there is no number to read: name the line and stop.
- **Headline figures** → the stable `totals.*` keys, e.g.
  `totals.net_profit.amount`, `totals.total_assets.amount`.
- **Dashboard KPI** → branch on `.unit`: `cents` → `.amount.amount` (dollars),
  `months` → `.amount` (integer), `bps` → `.amount` ÷ 100 (percent).
- **Tie-out** → compare the report's `*_check_delta` / `tieout.period_delta` to
  `0`, or `tie_out_ok` to `true`.

Never re-scale by 100 — values are already dollars.

## Report row maps & exact response shapes

Row numbers are **NOT stable across companies.** Every P&L band is elastic (one
row per expense function the company routes) and the Balance Sheet's assets come
out in that company's own routing order, so a row number learned on one company
names a different line on the next — with a real, plausible number on it.

Read a line by its **identity** instead, best source first: the `totals` block,
then a row's `role`, then `heading_key`, then `band_key`. If a line carries none
of them (account-level BS leaves like cash or receivables do not), report it as
*not identified* — never substitute a `0` or a row number.

`row_num` is legitimate as a sort key, and for `explain` / `drilldown` when it is
a number you read out of the response you are currently holding.

→ **`reference/report-reference.md`** — the identity vocabulary per report, the
field layout of every response, and one company's layout as an illustration.

## The answer contract — how to write the answer

These are the rules the in-app Lucid assistant answers by, adapted for your own
Claude. Every workflow skill's "Answering" section builds on them.

**Figures — quote, don't recompute.**
- Every number you state comes from a tool result. Copy it exactly: the
  envelope's `amount` and currency. Formatting for readability (`$`, thousands
  separators, `$1.2M` for a headline when the exact figure is also given) is
  fine. Rounding a figure you then reuse, rescaling or converting it is not.
- **Prefer a backend figure to a derived one.** Lucid already computes most
  things a CFO asks for: subtotals, margins, variances, `variance_pct`, the KPI
  strip (`get_status(sections=["kpis"])`: cash, runway, revenue, gross margin,
  operating profit, net profit, burn), MoM / QoQ / YoY comparison columns
  (`compare`), trends (`include_trend`) and composition (`include_composition`).
  Ask for them in the same call instead of computing them yourself.
- **Never re-add a subtotal from its leaves**, and never hand-sum monthly
  reports. Use the multi-period parameters (`periods`, `compare`, `include_trend`)
  so one call carries the series.
- **When something must be derived** (a ratio Lucid doesn't publish, a share of
  total, a what-if), compute it with the skill's bundled script or a few lines of
  code over the exact values, never by mental arithmetic. Say it is derived and
  from what: *"current ratio 2.1× (current assets ÷ current liabilities, both as
  reported)"*. Derived figures never replace a backend figure that exists.
- **Projected parts are always disclosed** (see *Projected entries* above), and
  the label carries into anything built on the figure.
- `null` is "no data", not zero. A row flagged `uncomputed: true` has no figure:
  name the line and say it isn't computed. Never fill either with `0`.

**Lead with the answer.** For a one-figure lookup, the first sentence is the
figure. For analysis, lead with the conclusion, then the drivers (what moved,
which direction, why), then the supporting figures, in a compact table when
there are more than three.

**Tie-out first.** State the reconciliation status before you lean on a report
(see *Tie-outs* above). A failed check is a headline, not a footnote; a check
that couldn't be evaluated is reported as exactly that.

**Voice — write for a CFO who has never seen inside Lucid.** They know
accounting, not our machinery.
- Never name internal things in the answer: no tool names (`get_pl`), no field
  names (`balance_check_delta`, `pool_configured`), no "backend", "API", "wire",
  "payload". Translate what an internal fact *means* for their books and where
  they would see it. For example, `pool_configured: false` becomes "no accounts
  are marked as bank accounts (Settings → Accounts)".
- Code font is for real account names and numbers only.
- No work log: don't narrate which tools you called, which periods you pulled or
  that you read a skill. The message is the answer.
- **A negative answer has one shape:** what's missing, in business terms; what it
  is *not* ("not set up" is not zero); then the one screen and action that fixes
  it, as a menu path (`get_help` and `get_check_catalogue` name the screens).
- **Never say or imply Lucid itself is at fault.** No "bug", "glitch", "known
  issue", "error in Lucid". When the data doesn't explain something, say it
  needs further investigation and list what you checked.

**Close with 2–3 short follow-ups** the user could ask next, grounded in what
you just found ("Drill into the G&A swing?", "Compare with the same month last
year?").

**Memory (if your Claude has it).** Lucid data is confidential.
- Personal preferences (how the user names reports, refers to periods, likes
  answers formatted, materiality thresholds for status checks) are fine to
  remember.
- **Never store a financial figure or company-specific financial fact in a
  memory that is not scoped to that company's work**, such as a global user
  profile that follows the user into unrelated chats. If the user asks you to
  remember a finding, keep it in a project or workspace scoped to that company,
  and say where you kept it.
- Never save a figure with a non-zero projected part as a fact: label it
  projected and date it, or don't save it.

## Which workflow skill to reach for

Classify the question into **one** intent and load only that skill. Route by
what the user means, not by a literal phrase match.

| Intent | The user wants… | Go to |
|---|---|---|
| Use the app | How to *do* something in Lucid, or a screen misbehaving ("how do I upload a chart of accounts", "where is the close", "why won't my import go through") | `lucid:product-help` |
| Look up a figure | One current number, no proof or analysis ("what's revenue for March", "cash balance") | no skill: resolve, fetch, quote it |
| Prove a figure | Verify, derive or trace one reported number ("why is X this number", "show the entries behind it", "tie this out") | `lucid:explain-and-audit` |
| Analyze one statement | Trend and drivers of one statement: P&L, margin, OpEx | `lucid:pl-and-margin-analysis` |
| | Balance sheet, liquidity, cash on hand, what we own / owe | `lucid:balance-sheet-review` |
| | Cash flow, burn, runway, where cash went | `lucid:cash-and-runway` |
| | Budget / plan variance | `lucid:budget-vs-actual` |
| Whole-business results | Financial results across statements ("how are we doing", a monthly / close review of the numbers) | `lucid:financial-position-review` |
| Workspace status | Operational state: what's pending or waiting on me, report health, what changed, "can we close?", "anything I should look at" | `lucid:workspace-status` |
| Investigate an issue | *Why* something looks wrong: a failing check, an odd figure, an account on an unexpected line, an empty month; or which accounts share a data gap | `lucid:investigate-data-issue` |
| Build a deliverable | A finished package ("board pack", "investor update", "export the financials") | `lucid:board-pack` |

Disambiguators:
- "How do I drill down" is *use the app*; "drill into this number" is *prove a figure*.
- One statement → its focused skill; the whole business → `financial-position-review`.
- Financial **results** across statements is *whole-business results*;
  operational **state** (work, breaks, changes, "can we close") is *workspace status*.
- Proving a number is *prove a figure*; a number, check or account placement
  that looks **wrong** is *investigate an issue*; a screen not working is *use the app*.
- A bare greeting isn't a status ask: reply in a line and offer a status check.
