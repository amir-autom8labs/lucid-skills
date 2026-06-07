---
name: pl-and-margin-analysis
description: >-
  Income-statement deep dive on the Lucid CFO connector — revenue, gross margin,
  OpEx composition and burn (R&D / S&M / G&A), operating income, EBITDA, and net
  profit, with MoM/QoQ/YoY trends and common-size (% of revenue). Use this
  WHENEVER the user asks about the "P&L", "income statement", "profit and loss",
  "gross margin" or "margin analysis", "are we profitable" / profitability,
  "OpEx" or operating expenses, "burn" or burn rate, "revenue trend" or growth,
  "common size", "EBITDA", "operating income", or "why did costs go up / why did
  margin drop". Pulls get_pl for the statement and get_dashboard for the
  margin/OpEx KPIs. Builds on lucid:lucid-platform-guide for the shared mechanics.
---

# P&L and margin analysis

Read an income statement the way an FP&A lead does: anchor on revenue, work down
through gross margin and the OpEx stack to operating income / EBITDA / net
profit, restate everything as a **% of revenue** so periods are comparable, then
explain the trend and the drivers. This skill is about *what to pull, in what
shape, and how to read it* — the connector mechanics (entity resolution, period
grammar, views, the money envelope, comparison gating, payload spill, the shared
helper) live in **`lucid:lucid-platform-guide`**. Read that first if you haven't;
don't restate it here.

## The five things that are specific to a P&L

**1. The P&L is a FLOW, not a snapshot.** Each figure is *activity over the
period*. To cover several months, **pass a wider period** — `2025-Q1`, `FY2025`,
`YTD@2025-06` — and let Lucid aggregate. **Never fetch monthly P&Ls and add them
up yourself**: you'll mishandle adjusting entries, cut-off, and intercompany, and
your subtotals will drift from the books. One wide call beats a hand-summed
stack of narrow ones. (Balance sheet is the opposite — a snapshot — but that's a
different skill.)

**2. The full statement is ~170 rows and SPILLS with `compare`.** A single-period
summary fits inline; add `compare` / `include_trend` / `include_composition` and
the result routinely exceeds the tool limit and the harness **spills it to a
file** (you get a path, not JSON). So:

- Default fetch: **one period, then read the `summary` section** (`row_num ≤ 30`)
  — that's revenue, margin, the OpEx lines, operating income, net profit, EBITDA.
- Drill into a **note section** (`row_num ≥ 33`) only when you actually need the
  composition of one line (e.g. "what's *in* G&A?").
- When a result spills, **do not read the raw JSON back into context.** Run the
  shared CLI against the file:

  ```bash
  python ${CLAUDE_PLUGIN_ROOT}/scripts/lucid_utils.py totals  pl.json
  python ${CLAUDE_PLUGIN_ROOT}/scripts/lucid_utils.py rows    pl.json --section summary --nonzero
  python ${CLAUDE_PLUGIN_ROOT}/scripts/lucid_utils.py rows    pl.json --section note --nonzero   # one note at a time
  ```

**3. Sign convention.** Revenue and expenses are **both positive**; subtotals are
revenue − expenses, so **a loss is negative**. Gross Margin, Operating Income,
Net Profit, EBITDA can all be negative — that's a loss, not a parse error. (A
negative *expense* line, by contrast, is a reclass / reversal / income offset
sitting in an expense row.)

**4. Comparisons: prefer explicit `periods=` over `compare`.** Both add columns,
but the per-row `series` array **is not labelled** with its periods. With
`compare="qoq"` you can't be certain which trailing quarters you got; with
`periods="2025-Q1,2025-Q2,2025-Q3"` *you* set the order, so every column is
identifiable. Use `compare` only for a quick eyeball. And respect the gating
matrix — the primary period's *kind* limits which `compare` values are legal:

| primary kind | mom | qoq | yoy |
|---|---|---|---|
| month | ✅ | ✅ | ✅ |
| quarter | ❌ | ✅ | ✅ |
| half / ytd / fy / range | ❌ | ❌ | ✅ |

(An illegal pair returns a 400.) Either way, multi-period = a bigger payload that
may spill — see point 2.

**5. Common-size = each line ÷ revenue.** This is the single most useful
transform on a P&L: restate every row as a % of revenue (`row / totals.revenues`,
i.e. `row / row 5`). It normalizes for company size and reveals whether a line is
growing *faster or slower than the top line* — the thing a raw dollar delta
hides. Revenue is always 100%; COGS % and the three OpEx %s are what you compare
over time and against plan.

## Headline rows (you'll reference these constantly)

Row numbers and labels are **configured per company**, so treat the numbers below
as the typical layout, not a guarantee — confirm them against the actual response,
and prefer the stable `totals.*` keys for headline figures. (Full map in
`lucid:lucid-platform-guide` → `reference/report-reference.md`.)

| row | line | | row | line |
|---|---|---|---|---|
| 5 | Revenues | | 13 | **Total OpEx** (subtotal) |
| 6 | COGS | | 15 | **Operating income / (Loss)** |
| **7** | **Gross Margin** (subtotal) | | 19 | Income (Loss) before tax |
| 8 | % Gross Margin | | 24 | **Net Profit / (Loss)** |
| 10 / 11 / 12 | **R&D / S&M / G&A** | | 30 | **EBITDA** |

OpEx burn = rows 10 + 11 + 12 = row 13. To explain *why an OpEx line moved*, open
its note: R&D = Note 3 (86–106), S&M = Note 4 (109–137), G&A = Note 5 (140–175);
payroll, contractors, and servers/hosting are usually the swing items.

`totals` carries the same headline figures plus the **tie-out**:
`{revenues, gross_margin, operating_income, ebitda, net_profit, check_delta}`.
**`check_delta` must be `0`** — if not, say so prominently and treat the figures
as suspect (see the platform guide's tie-out discipline).

## Recommended workflow

1. **Resolve the entity** (`search_entities` → exact `code`). Confirm it's the
   right level — a parent/root consolidates subs.
2. **Pick the period as a flow.** Single period for a point-in-time read; a wide
   period (`FY2025`, `2025-Q3`) for a span; explicit `periods=` for a labelled
   trend.
3. **Fetch compactly** — one call, read `section="summary"` first. Add notes or a
   trend only when the question needs them.
4. **Tie out** — check `totals.check_delta == 0` before quoting anything.
5. **Compute common-size and (if multi-period) growth** with the script below.
6. **Read drivers, not just deltas** — open the note for any line that moved
   materially; use `explain` / `drilldown` (see `lucid:explain-and-audit`) for the
   "why is *this* number this" follow-up.

## The common-size / growth script

`scripts/common_size.py` builds a common-size P&L (every headline row as a % of
revenue) and, with `--growth`, a period-over-period change table across the
`series`. It imports the shared `lucid_utils` (so money parsing and ratios match
every other skill) and reads a path or `-` (stdin), including a spilled file.

```bash
# Common-size, single period:
python ${CLAUDE_PLUGIN_ROOT}/skills/pl-and-margin-analysis/scripts/common_size.py pl.json

# Growth across a labelled multi-period payload (fetched with periods=):
python ${CLAUDE_PLUGIN_ROOT}/skills/pl-and-margin-analysis/scripts/common_size.py \
    pl_multi.json --growth --labels 2025-Q1,2025-Q2,2025-Q3
```

It prints a tie-out warning to stderr if `check_delta` is off, so a broken close
can't slip through silently.

## Worked example — fictional company (Acme Inc.), synthetic figures

*Illustrative example — fictional company (Acme Inc.), synthetic figures.*

`get_pl(company="ACME", period="2025-Q1")` — single period, summary fits inline,
no spill. Headline figures (tie-out `check_delta = $0` ✓):

| line | amount | % of revenue |
|---|---:|---:|
| Revenues | $250,000 | 100.0% |
| COGS | $300,000 | 120.0% |
| **Gross Margin** | **−$50,000** | **−20.0%** |
| R&D | $400,000 | 160% |
| S&M | $300,000 | 120% |
| G&A | $150,000 | 60% |
| **Total OpEx** | **$850,000** | 340% |
| **Operating income** | **−$900,000** | — |
| **Net Profit** | **−$880,000** | — |
| **EBITDA** | **−$890,000** | — |

**The finding to lead with: gross margin is *negative*.** COGS ($300,000) exceeds
revenue ($250,000), so the company loses money on delivery *before any OpEx* —
gross margin is −$50,000, a −20.0% gross margin. (The dashboard's gross-margin KPI
reads **−20.00%** — same story; the bps unit `-2000` ÷ 100.) That is the headline,
not the net loss: a sub-scale ARR against a fixed servers/hosting + COGS-payroll
base. Until revenue clears COGS, OpEx discipline alone can't reach profitability.

Below the line, OpEx dwarfs revenue (~3.4x), with **R&D the largest block**
($400k, ~47% of OpEx) — an early-stage build profile. Net loss of $880k and
EBITDA of −$890k (EBITDA sits just above operating income here because
depreciation and the net financial line are small relative to the loss).

## Output structure for a margin analysis

Lead with the punchline, then support it. Always show the tie-out.

1. **Revenue** — level, period basis (flow), and trend (growth % if multi-period).
2. **Gross margin & drivers** — GM $ and GM %; what's in COGS that moved it
   (servers/hosting, COGS payroll). Flag a negative or thin GM loudly.
3. **OpEx breakdown** — R&D / S&M / G&A in $ and % of revenue; total burn;
   biggest line and biggest mover (open the note to name the swing item).
4. **Profitability** — operating income, net profit, **EBITDA**; each in $ and,
   where meaningful, % of revenue.
5. **Trend** — MoM/QoQ/YoY on the headline rows (use `periods=` for labelled
   columns); call out whether margins are improving or eroding.
6. **Flags + tie-out** — negative/abnormal margins, expense lines with the wrong
   sign, and an explicit **`check_delta = $0` ✓** (or a prominent warning if not).
   State the `view` you used (`lucid` by default).
