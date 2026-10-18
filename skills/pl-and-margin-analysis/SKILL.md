---
name: pl-and-margin-analysis
description: >-
  analyze-statement intent for the P&L: income-statement deep dive on the Lucid
  connector — revenue, gross margin, OpEx composition (R&D / S&M / G&A), operating
  income, EBITDA, and net profit, with MoM/QoQ/YoY trends and common-size (% of
  revenue). Use this WHENEVER the user analyzes the "P&L", "income statement", "profit
  and loss", "gross margin" or "margin analysis", profitability / "are we profitable",
  "OpEx" or operating expenses, "revenue trend" or growth, "common size", "EBITDA",
  "operating income", or "why did costs go up / why did margin DROP" (the trend and its
  drivers over time). Do NOT use it for: cash BURN or RUNWAY / "how long will cash last"
  → that is cash-and-runway (spending OpEx on the P&L is not cash burn); proving ONE
  figure ("why is THIS number, break it down, show the entries behind it") →
  explain-and-audit; the cross-statement "how are we doing" snapshot →
  financial-position-review; a packaged board/investor deliverable → board-pack.
---

# P&L and margin analysis

Read an income statement the way an FP&A lead does: anchor on revenue, work down
through gross margin and the OpEx stack to operating income / EBITDA / net
profit, restate everything as a **% of revenue** so periods are comparable, then
explain the trend and the drivers. This skill is about *what to pull, in what
shape, and how to read it* — the connector mechanics (entity resolution, period
grammar, views, the money envelope, comparison gating) live in the tool
docstrings and the system prompt; don't restate them here.

## The five things that are specific to a P&L

**1. The P&L is a FLOW, not a snapshot.** Each figure is *activity over the
period*. To cover several months, **pass a wider period** — `2025-Q1`, `FY2025`,
`YTD@2025-06` — and let Lucid aggregate. **Never fetch monthly P&Ls and add them
up yourself**: you'll mishandle adjusting entries, cut-off, and intercompany, and
your subtotals will drift from the books. One wide call beats a hand-summed
stack of narrow ones. (Balance sheet is the opposite — a snapshot — but that's a
different skill.)

**2. Fetch `density=summary` — the summary payload fits inline.** The full
statement is ~170 rows and, with `compare`, spills to a file. You almost never
need that: pass **`density=summary`** and `get_pl` returns just the ~25 category
rows (`row_num ≤ 30`) — revenue, margin, the OpEx lines, operating income, net
profit, EBITDA — each carrying its `row_num`, `label`, `amount`, `series`. That's
the whole margin story in a small inline payload, and every figure is addressable
by `row_num` for the answer selection. So:

- Default fetch: **one period, `density=summary`.** Reads inline; no spill.
- Drill a **statement block** — pass `section=opex` (or `revenue`, `cogs`,
  `finance`, `other`; a fixed closed set, so no guessing) — only when you actually
  need the composition of one line. **R&D / S&M / G&A all live inside `opex`**, so to
  break down any of them (e.g. "what's *in* G&A?") drill `section=opex` and read its
  sub-rows; the block payload carries its subtotal rows and their leaf accounts.
- If a heavier pull (`compare`, a full statement) does spill to a file, **don't
  read the raw JSON back into context.** Run the shared CLI (relative path from the
  skill dir) against the file:

  ```bash
  python scripts/lucid_utils.py totals  pl.json
  python scripts/lucid_utils.py rows    pl.json --section summary --nonzero
  python scripts/lucid_utils.py rows    pl.json --section note --nonzero   # one note at a time
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
transform on a P&L: restate every row as a % of revenue (`row /
totals.revenues`, falling back to the row whose `heading_key` is `revenues` —
never to a row number). It normalizes for company size and reveals whether a line
is growing *faster or slower than the top line* — the thing a raw dollar delta
hides. Revenue is always 100%; COGS % and each OpEx function's % are what you
compare over time and against plan. **How many OpEx functions there are is a
property of the company** — map over the `operating_expenses` band, do not assume
three.

A zero-revenue period is a real answer, not a missing one: say common-size is
undefined for it. Do not fall back to another line's value.

## Headline rows (you'll reference these constantly)

Row numbers and labels are **configured per company**, so treat the numbers below
as the typical layout, not a guarantee — confirm them against the actual response,
and prefer the stable `totals.*` keys for headline figures. (Full map in
`reference/report-reference.md`.)

| row | line | | row | line |
|---|---|---|---|---|
| 5 | Revenues | | 13 | **Total OpEx** (subtotal) |
| 6 | COGS | | 15 | **Operating income / (Loss)** |
| **7** | **Gross Margin** (subtotal) | | 19 | Income (Loss) before tax |
| 10 / 11 / 12 | **R&D / S&M / G&A** | | 24 | **Net Profit / (Loss)** |
| | | | 30 | **EBITDA** |

OpEx burn = the `total_opex` subtotal (`role: total_opex`) — read it, do not
add the function rows up yourself: the backend already summed them, the band
holds however many functions the tenant routes (not three), and re-summing is an
invariant-#8 violation. To explain *why an OpEx line moved*, open
its note: R&D = Note 3 (86–106), S&M = Note 4 (109–137), G&A = Note 5 (140–175);
payroll, contractors, and servers/hosting are usually the swing items.

`totals` carries the same headline figures plus the **tie-out**:
`{revenues, gross_margin, operating_income, ebitda, net_profit, ledger_net_profit,
check_delta, check_unresolved}`. `ledger_net_profit` is Net Profit summed straight off
the classified ledger; `check_delta` is `ledger_net_profit − net_profit`.
**`check_delta` must be `0`** — if not, say so prominently and treat the figures
as suspect (a books problem worth surfacing).
**A `0` only counts when `check_unresolved` is empty.** That field lists the reasons an
operand could not be resolved; while it is non-empty the `0` is a placeholder, not a
tie-out — report "not evaluated" and quote the reason, never "the P&L ties out".

## Recommended workflow

1. **Resolve the entity** (`search_entities` → exact `code`). Confirm it's the
   right level — a parent/root consolidates subs.
2. **Pick the period as a flow.** Single period for a point-in-time read; a wide
   period (`FY2025`, `2025-Q3`) for a span; explicit `periods=` for a labelled
   trend.
3. **Fetch compactly** — one `get_pl(..., density=summary)` call; it reads inline
   with every headline row and its `row_num`. Add a `section` block drill or a trend
   only when the question needs it.
4. **Tie out** — check `totals.check_delta == 0` **and** `totals.check_unresolved`
   empty before quoting anything. A `0` beside a non-empty `check_unresolved` is an
   unevaluated control, not a pass.
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
python scripts/common_size.py pl.json

# Growth across a labelled multi-period payload (fetched with periods=):
python scripts/common_size.py \
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

## Answering

Follow the answer contract in `lucid-platform-guide`, applied to a margin read.

Walk down the statement: revenue level and direction; whether gross margin is
healthy / thin / negative and *why* (which COGS driver moved it — servers/hosting,
COGS payroll); how the OpEx stack sits and which block is the swing; and where
profitability lands (operating income, net profit, EBITDA), improving or eroding.

- **Quote the headline figures** — revenue, gross margin, total OpEx, operating
  income, net profit, EBITDA — from `totals` / the role rows, in a compact table
  when you show more than three. Read the margin percentages Lucid publishes
  rather than dividing them out.
- **Trends come from the wire**: ask for `compare` (MoM / QoQ / YoY, within the
  compare-gating matrix above) or `periods` / `include_trend`, and quote the
  comparison columns and deltas the report returns.
- **Common-size (% of revenue) is derived**: run `scripts/common_size.py` over the
  report and quote its output, labelled "% of revenue". If the script refuses a
  column (no revenue denominator on the wire), say so — don't fill it in.
- Close with 2–3 follow-ups such as "Open the G&A detail for the swing line?" or
  "Compare this quarter against last year?".

Lead with the tie-out: if `check_delta ≠ 0`, or if `check_unresolved` is non-empty
(the tie-out could not be evaluated at all), say so plainly and treat the figures
as provisional — a broken or unevaluated close outranks any margin insight.
State the `view` you used (`lucid` by default).

**An open month carries projected entries.** In `lucid`, the recurring expenses
not yet booked in an open month (payroll, rent, subscriptions) are filled with
projected entries, so the month is comparable to the months before it. Every
row with a projected part carries `projected` and `basis: "projected"`. **For any
open month you report, state the projected part** of each figure you quote that
has one ("operating expenses $480k, of which $310k projected"), and of any
margin built on it. Never present a projected margin as a booked one. Asked for
"what is actually booked", pass `include_projections=false`.
