---
name: budget-vs-actual
description: >-
  Budget-vs-actual variance analysis from the Lucid CFO connector — answers "are
  we on budget", "BVA", "did we hit our numbers", "where are we vs plan", "what's
  our budget variance", "are we over/under plan", "where are we overspending",
  and any favorable/unfavorable variance question. Use this WHENEVER the user
  compares actuals to plan/budget: ranking variances by materiality, splitting
  favorable from unfavorable, and explaining the drivers behind the miss. Pulls
  Lucid's get_bva (a P&L with actual/budget/variance per row) and reads it with
  the correct sign interpretation per section (over-spending an expense is bad;
  missing a revenue target is bad). Builds on lucid:lucid-platform-guide.
---

# Budget vs Actual (variance analysis)

Answer three questions, in order: **where are we vs plan, by how much, and why.**
Then rank the misses by materiality and label each one favorable or unfavorable
using the *business* meaning, not the raw arithmetic sign. The whole craft here is
that `variance = actual − budget` has the same sign for a revenue line and a cost
line, but the opposite implication — so a mechanical "positive = good" reading is
wrong half the time.

Read `lucid:lucid-platform-guide` first for the mechanics this skill assumes:
entity resolution, period grammar, view modes, the money envelope, the tie-out
discipline, and how to handle spilled payloads. This skill only covers what is
specific to BVA.

## What get_bva gives you

`get_bva(company, period, view)` returns a **P&L skeleton** — the same row map as
`get_pl` — but every row carries `{actual, budget, variance, variance_pct}`
instead of a single `amount`.

- **Same row numbers as the P&L** (typical headline rows): Revenues · Gross
  Margin · Total operating expenses · Operating income · Net Profit · EBITDA ·
  Total expenses, with detail in the note rows below them (Revenue, COGS, R&D,
  S&M, G&A, Financial, Other, Taxes). **Row numbers and labels are configured
  per company**, so don't hard-code them — prefer the stable `totals.*` keys
  (`revenues_actual`/`_budget`/`_variance`, etc.) and resolve detail rows by
  label/section. (Full map: the P&L section of `reference/report-reference.md` in
  the platform guide.)
- **`view` applies to the ACTUAL side only.** The budget is **view-invariant** —
  `base`, `aje`, and `lucid` all return the same budget. So `base` vs `lucid`
  changes only the actual column (and therefore the variance). Default to `lucid`.
- **`variance = actual − budget`.** **`variance_pct = variance / |budget|`** as a
  **float fraction** (`0.479` = +47.9%), and **`null` when `budget == 0`** — a row
  with no plan mapping has an undefined percentage, not a zero one.
- **`totals`** carries `revenues_*`, `total_expenses_*`, `operating_income_*`,
  `net_profit_*` (each split `_actual` / `_budget` / `_variance`) plus
  **`check_delta`** — the tie-out. `check_delta == 0` means the actual side
  reconciles to the books; if it's non-zero, say so loudly and treat the figures
  as suspect.

## Interpreting variance — the sign flips by line type

This is the part to get right:

| Row type | `variance > 0` (actual above budget) | `variance < 0` (actual below budget) |
|---|---|---|
| **Revenue** / margin / profit subtotals | **FAVORABLE** — beat the plan | **UNFAVORABLE** — under-performed |
| **Expense** / cost lines | **UNFAVORABLE** — over-spent | **FAVORABLE** — came in under |

So on the income statement, a positive variance on Revenue is good, but a
positive variance on S&M is bad. The profit subtotals (Gross Margin, Operating
Income, Net Profit, EBITDA) read like revenue — higher is better. Cost lines
(COGS, R&D, S&M, G&A, Total OpEx, Financial, Other, Taxes, Total expenses,
Depreciation, and every expense note row) read the other way. **Never label a
variance from the sign alone — resolve it by the row's role.** The script below
encodes exactly this mapping. (Row numbers/labels are configured per company —
see `reference/report-reference.md` in the platform guide; classify by section,
not by a fixed row number.)

## Materiality — rank, don't list

A BVA has ~170 rows; most variances are noise. Surface what moves the number:

1. **Rank by `|variance|`** (absolute dollars). The shared helper's
   `variance_table(bva, top=N)` already does this. The biggest dollar misses are
   what the CFO acts on.
2. **Flag the outliers:** a row deserves a callout when `|variance_pct|` is large
   **AND** `|variance|` is material. A +150% variance off an $80K budget and a
   +20% variance off a $700K budget are both "large %", but the big-dollar one is
   the real story; a tiny-budget % spike only matters if it's also big in dollars.
   Conversely a $5 miss at ∞% is nothing. Require both — a dollar floor (default
   $10K) and a % bar (default ±25%) — so tiny budgets don't generate false alarms.
3. **Handle null `variance_pct` gracefully.** Budget 0 → percentage is undefined;
   show "n/a", not "0%" or "∞%", and judge those rows on dollars alone. These are
   often lines that exist in actuals but were never mapped in the plan (or vice
   versa) — worth a one-line callout because the plan structure differs from how
   the business actually ran.

## Retrieve compactly

BVA is a flow (see period grammar) and spills past the tool-result limit, so:

- Pull **one period, single column of interest, no comparisons.** Do **not** pass
  `compare`, `periods`, `include_trend`, or `include_composition` — this skill is
  single-period variance, and those balloon the payload.
- Pick the period to match the question: a month (`2025-03`), a quarter
  (`2025-Q1`), or the year (`FY2025`). Don't sum months yourself — widen the period.
- When the result spills to a file, **don't read the raw JSON.** Drive the shared
  helper's `bva` subcommand and the variance-report script against the path:

  ```bash
  python ${CLAUDE_PLUGIN_ROOT}/scripts/lucid_utils.py bva <spilled.json> --top 12
  python ${CLAUDE_PLUGIN_ROOT}/scripts/lucid_utils.py totals <spilled.json>
  python ${CLAUDE_PLUGIN_ROOT}/skills/budget-vs-actual/scripts/variance_report.py <spilled.json> --top 10
  ```

## Workflow

1. **Resolve the company** (`search_entities` → exact `code`) and pick the period
   + view (default `lucid`).
2. **Call `get_bva(company, period)`** once. Expect a spill; note the file path.
3. **Check the tie-out** — `totals.check_delta == 0` — before trusting anything.
4. **Read the headline** from `totals`: revenue actual vs budget, total expenses
   actual vs budget, net profit actual vs budget, each with its variance.
5. **Rank the drivers** with `variance_report.py` (or `lucid_utils.py bva --top`),
   split favorable vs unfavorable, flag the material outliers.
6. **Explain the why.** For the top variances, name the driver (which note/line),
   and if the user wants the journal-level cause, hand off to
   `lucid:explain-and-audit` (`explain`/`drilldown` on the BVA cell, column
   `actual` / `budget` / `variance`).

## The variance-report script

`scripts/variance_report.py` (stdlib + `lucid_utils`) builds the ranked report:
headline actual/budget/variance for revenue / OpEx / operating income / net
profit; the top-N variances by `|variance|` split into **UNFAVORABLE** and
**FAVORABLE** with the per-section sign rule applied; a material flag; the
variance % (or "n/a" for budget-0 rows); and the tie-out line.

```bash
python ${CLAUDE_PLUGIN_ROOT}/skills/budget-vs-actual/scripts/variance_report.py \
    <bva.json> --top 10 --material 10000
```

## Worked example

*Illustrative example — fictional company (Acme Inc.), synthetic figures.*

Demonstrate on **company ACME, period `2025-03`** (single period, no compare). The
`get_bva` call spills to a file; run the helper / script on that path. Output:

```
$ python lucid_utils.py totals <bva.json>
   revenues_actual:   $250,000     revenues_budget:  $350,000   revenues_variance:  -$100,000
   total_expenses_actual: $850,000  total_expenses_budget: $700,000  total_expenses_variance: $150,000
   net_profit_actual: -$880,000   net_profit_budget: -$430,000  net_profit_variance: -$450,000
   check_delta: $0      tie-out: OK

$ python variance_report.py <bva.json> --top 10
HEADLINE  (actual vs plan)
  Revenue          actual   $250,000   budget   $350,000   var  -$100,000  [UNFAVORABLE]
  Total OpEx       actual   $850,000   budget   $700,000   var   $150,000  [UNFAVORABLE]
  Gross margin     actual   -$50,000   budget    $50,000   var  -$100,000  [UNFAVORABLE]
  Net profit       actual  -$880,000   budget  -$430,000   var  -$450,000  [UNFAVORABLE]

UNFAVORABLE (worst misses first)
  *[ S&M ]   Sales & marketing        var  $120,000 (+150.0%)  <-- large % on material base
  *[ Rev ]   Revenues                 var -$100,000  (-28.6%)  <-- large % on material base
  *[ OpEx]   Total operating expenses var  $150,000  (+21.4%)  <-- large % on material base
  *[ G&A ]   General & admin          var   $30,000      (n/a)
FAVORABLE (best beats first)
  *[ R&D ]   Research & development   var  -$40,000  (-40.0%)
TIE-OUT: OK  (check_delta $0)
```

How to read this for Acme's March 2025:

- **Books tie out** (`check_delta = $0`) — safe to present.
- **Revenue missed plan:** $250,000 actual vs $350,000 budget, **−$100,000
  (−28.6%)** — unfavorable (under-performance on revenue). This is the top-line story.
- **OpEx over plan:** total expenses $850,000 vs $700,000 budget, **+$150,000
  (+21.4%)** unfavorable, driven largely by **S&M +$120,000 (+150%)** off an
  $80,000 plan — both material in dollars and large in %, the clearest single
  driver. (A large % alone wouldn't qualify; the $120K does.)
- **The two compound:** revenue shortfall + OpEx overrun push **net profit to
  −$880,000 vs a −$430,000 plan, $450,000 worse than budgeted**, and turn gross
  margin negative (−$50,000 actual vs +$50,000 plan).
- **Plan-mapping quirks:** the G&A line shows a **null `variance_pct` ("n/a")**
  because its budget mapped to $0 while $30,000 of actual spend landed there —
  judge it on dollars, not %. Likewise treat any ±100% rows as structure
  mismatches rather than real outperformance. Watching for these is why we judge
  on dollars, not %.

If the live `get_bva` call fails or RLS blocks the company, run the same workflow
on any company you can access and describe the structure generically — the
interpretation rules above don't change.

## Output structure

Present in this order:

1. **Tie-out** — state `check_delta` first (one line). If non-zero, lead with the
   warning; the variances are unreliable until the books reconcile.
2. **Headline** — Revenue, Total expenses (or OpEx), Operating income, Net profit:
   actual vs budget vs variance, each tagged favorable/unfavorable.
3. **Top unfavorable** — the material misses (worst dollars first), each with $
   variance, %, and the driver line.
4. **Top favorable** — the material beats, same shape.
5. **Drivers / commentary** — 2–4 sentences: what moved the number and why
   (revenue shortfall, specific cost overruns), and any null-/±100%-% plan-mapping
   caveats. Offer `lucid:explain-and-audit` for the journal-level cause.

Keep it scannable; rank by materiality; never bury the lede (usually net profit
vs plan) under leaf detail.
