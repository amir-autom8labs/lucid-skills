---
name: financial-position-review
description: >-
  cross-statement-snapshot intent: the monthly-close / "how are we doing"
  WHOLE-BUSINESS snapshot on the Lucid connector. Dashboard-led health check ACROSS
  every statement — pull the dashboard, corroborate against P&L, balance-sheet, and
  cash-flow totals, verify EVERY report's tie-out, and produce a tight CFO-grade summary
  (position, profitability, liquidity, cash trajectory, risks) citing real figures. USE
  THIS WHENEVER someone wants the OVERALL state of the business rather than one
  statement — "how are we doing", "monthly review", "close review", "financial health",
  "state of the business", "where do we stand", "month-end summary", "snapshot of
  {company} for {month}". Do NOT use it when the ask is scoped to ONE statement: just
  the balance sheet / liquidity / "financial position as of a date" → balance-sheet-
  review; just P&L → pl-and-margin-analysis; just cash / burn → cash-and-runway; just
  budget → budget-vs-actual. A packaged export/board deck → board-pack.
---

# Financial position review (the close snapshot)

This is the **"how are we doing" answer**: not one statement, but a single
coherent read across all of them. A CFO closing the month wants four things at
once — where do we *stand* (position), are we *making money* (profitability),
can we *pay our bills* (liquidity), and where is *cash heading* (trajectory) —
plus an honest list of risks. Your job is to assemble that from the three core
statements (P&L, balance sheet, cash flow), **prove each one ties out**, and write
it up so a busy executive trusts it at a glance.

**A close review starts with status.** When the ask is a close / period review,
first call `get_status(sections=["health","pending"])` and **lead with any blocking
items** — broken tie-outs, unclassified movement, held entries, pending work — before
the financial snapshot. A review of numbers you can't yet close on is misleading, so
name what's blocking the close up front, then give the position read below.

> The connector mechanics this skill assumes — entity resolution, period grammar
> (`2025-03`, `FY2025`, `YTD@…`), view modes (`base`/`aje`/`lucid`), the money
> envelope, and comparison gating — live in the tool docstrings and the system
> prompt. This skill does **not** repeat them. It *does* restate two things —
> tie-out discipline and compact retrieval — because they are the spine of a review.

## Framing the month — the KPI bundle is back

> **Projected entries.** In an open month the `lucid` figures (reports and the
> KPI bundle) include Lucid's projections of recurring P&L entries not booked
> yet. A KPI whose figure includes projections carries `basis: "projected"`
> (and, for a money KPI, its `projected` part): state it beside the figure
> ("operating profit $120k, with $95k of the costs under it projected"). Cash, burn,
> runway and the month's story are booked, as are health checks and close
> readiness.

`get_status(company, period=…, sections=["kpis", "moved"])` frames a review in
one call: the headline KPIs (**cash · runway · revenue · gross margin ·
operating profit · net profit · burn**) and the month's largest changes, both
computed once in the backend — the same figures the CFO dashboard draws.
The old `get_dashboard` is withdrawn; this is its
replacement, and it is **opt-in**, so those sections must be named.

Use it to *frame*, then still pull the three statements to *review*: the bundle
carries no statement lines, no account detail and no tie-out arithmetic. Quote
its figures verbatim (money is already in major units — **never divide by 100**;
`runway` is months and `gross_margin` is basis points) and never recompute one
off a statement, which would put two numbers for one month in front of the
reader.

So the shape of a review is: **frame with `get_status` → pull P&L / BS / CF →
tie-out on all three → write up.**

## Tie-out discipline (non-negotiable here)

A position review that quietly presents a number from books that don't reconcile
is worse than no review. **Check every report's reconciliation before you trust
a single figure**, and surface the result explicitly — your summary must carry a
literal `Tie-out: OK` / `Tie-out: OFF` line.

| Report | Check field | Tied out when |
|---|---|---|
| P&L | `totals.check_delta` | `= 0` **and** `totals.check_unresolved` empty |
| Balance sheet | `totals.balance_check_delta` | `= 0` |
| Cash flow | `tieout.period_delta` | `= 0` |

If **any** is off, say so prominently at the top, name which report, and treat
its figures as provisional. One OFF report taints the whole snapshot's
credibility — don't bury it.

## Compact retrieval (don't blow up context)

These reports are large (a P&L is ~170 rows). For a review you only need the
**`totals` block and a handful of subtotal rows** — never the leaf detail. So:

- Pull **one period, one view, `density=summary`, no extras.**
  `density=summary` returns just the ~25 category rows (each with its `row_num`)
  plus the `totals` block — exactly what a review needs, read inline. Do **not**
  pass `compare` / `include_trend` / `include_composition` — they multiply the
  payload and can overflow the tool result. If you want a prior-period delta for
  the headline, add a single `compare` on the P&L only.
- If a heavier tool result **spills to a file**, do not read the raw JSON back.
  Run the shared helper or `position_review.py` (relative path `scripts/…`)
  against the file path instead.

## The worked flow — company ACME, 2025-03, view `lucid`

> **Illustrative example — fictional company (Acme Inc.), synthetic figures.**
> All numbers below are made up and internally consistent for teaching; they are
> not real client data.

### 1. Resolve, then frame from the statements

```text
search_entities("Acme") → code "ACME"        # never guess a handle
```

The headline figures come from `get_status(sections=["kpis"])` (above); the
statements you pull in step 2 carry the detail behind them — **cash** in the
balance-sheet `totals.cash`, **revenue / gross margin / EBITDA** in the P&L `totals`,
**cash movement** in the cash-flow `totals`. Cite the KPI card for a headline and
the statement for what is inside it; do not quote both as two figures. (Watch
units either way: money envelopes are already in major units — **never divide by
100**.)

For Acme Inc. / Mar 2025 the headline frame reads:

| Figure | Source | Value |
|---|---|---|
| Cash | BS `totals.cash` | **$8,000,000** (−$480,000 vs Feb 2025) |
| Runway | `get_status` `kpis` | **18 months** (quoted from the card) |
| Revenue (Q1) | P&L `totals` | **$250,000** (−40% YoY vs Q1 2024) |
| Gross margin (Q1) | P&L `totals` | **−20.00%** |

OpEx (from the P&L notes): R&D $400,000 · S&M $300,000 · G&A $150,000 =
**$850,000 total**. So the frame is: well-capitalized but revenue has collapsed
YoY and gross margin is *negative* — selling below cost. That's the thread to pull
on in the statements.

### 2. Corroborate against the three statements

Pull each as a **single period, no extras**, and save to files:

```text
get_pl(company="ACME", period="2025-Q1", view="lucid", density="summary")          → pl.json
get_balance_sheet(company="ACME", period="2025-03", view="lucid", density="summary") → bs.json
get_cash_flow_direct(company="ACME", period="2025-03", view="lucid", density="summary") → cf.json
```

> Period note: revenue/margin are most useful **quarter-to-date**, so pull the
> P&L for `2025-Q1`; balance sheet and cash flow are read at/through the month
> `2025-03`.

Pull just the totals + tie-out from each spilled file:

```bash
python scripts/lucid_utils.py totals pl.json
python scripts/lucid_utils.py totals bs.json
python scripts/lucid_utils.py totals cf.json
```

Validated figures for Acme Inc. (synthetic):

- **P&L (Q1-2025):** net_profit **−$880,000**, gross_margin **−$50,000**,
  ebitda **−$890,000**, `check_delta $0`. → this is where the negative gross
  margin comes from; the quarter is deeply loss-making.
- **Balance sheet (Mar 2025):** total_assets **$8,200,000**, total_equity
  **−$4,400,000** wire → **+$4.4M positive equity** once sign-flipped
  (assets $8.2M = liabilities $3.8M + equity $4.4M), `balance_check_delta $0`. →
  assets are almost entirely the cash pile; equity is positive but being eroded
  by accumulated losses (~$15.0M paid-in vs ~$10.6M cumulative losses).
- **Cash flow (Mar 2025):** net_operating **−$450,000**, net_investing
  **−$30,000**, total_change **−$480,000**, `tieout.period_delta $0`. → the
  −$480,000 **equals the −$480,000 move in the balance-sheet cash figure** —
  corroboration achieved. Burn is operating, not investing.

### 3. Verify all three tie-outs at once

`position_review.py` consolidates the snapshot and, most importantly, lays the
three reconciliations side by side so nothing slips through:

```bash
python scripts/position_review.py \
    --pl pl.json --bs bs.json --cf cf.json
```

All three read `OK` (delta $0) for Acme Mar 2025 → the snapshot is trustworthy.
Had any read `OFF`, the script flags `OVERALL: OFF` and you lead your write-up
with that. (The script still accepts an optional `--dashboard` input for when the
KPI bundle returns, but that tool is withdrawn today — don't pass it.)

> **How this script names lines.** `position_review.py` resolves every figure by
> IDENTITY — the `totals` block first, then a row's `role` (`gross_margin`,
> `operating_income`, `net_profit`, `ebitda`, `total_assets`, `total_equity`),
> and `heading_key: revenues` for the top line. It reads no row numbers, because
> a row number names a different line on every company whose layout differs from
> the reference chart's. Apply the same rule to anything you compute yourself:
> see the foundation guide's `reference/report-reference.md` for the identity
> vocabulary per report.

### 4. Write it up

Map the corroborated figures into the output template below. Lead with the
tie-out line, then position → profitability → liquidity & cash → risks.

## Answering

A position review is the widest answer this connector produces, so the answer
contract in `lucid-platform-guide` matters most here.

Write the snapshot in this order:

1. **Tie-out first.** If any of the three reconciliations is off, lead with it *by
   name* and call the figures provisional — one OFF report taints the whole snapshot.
2. **Headline** — the state of the business in one or two sentences
   (well-capitalized vs stretched; growing vs contracting; profitable vs burning).
3. **Profitability** — revenue direction, margin health and its driver, where the
   result lands.
4. **Liquidity & cash** — cash trend and the cash cushion against burn. **The
   runway is the `get_status` `kpis` card, quoted, never divided out of the
   statements** (when its amount is `null`, give its `comparator`'s reason: a
   month that is not burning has no runway clock). Then equity structure
   (positive vs eroding vs deficit — read the sign carefully) and where cash went.
5. **Risks & flags** — the 2–4 things a CFO acts on.

Back the narrative with a compact scorecard of quoted figures: the KPI strip
(cash, runway, revenue, gross margin, operating profit, net profit, burn) plus
total assets, total equity and net operating cash, each from its tool result.
Always name the **view and period** — the figures are meaningless without them.
Close with 2–3 follow-ups such as "Drill into what's driving the operating
burn?" or "Compare this month against last?".

### Worked example (Acme Inc., 2025-03) — the shape of the answer

**Illustrative example — fictional company (Acme Inc.), synthetic figures.**

> *"Acme is well-funded but unprofitable. Tie-outs pass on all three statements,
> so the picture is trustworthy. Cash is $8.0M against a monthly operating burn
> of $440k — 18 months of runway on Lucid's own runway figure. But Q1 revenue is
> down sharply year-over-year and gross margin is negative: Acme is selling below
> cost while carrying a full OpEx base, so the loss is structural, not a one-off.
> Cash is draining through operations, not investing or financing, and book
> equity — still positive at $4.4M — erodes with each loss-making quarter.*
>
> | | Mar-2025 |
> |---|---:|
> | Cash | $8,000,000 |
> | Runway | 18 months |
> | Net profit | −$480,000 |
> | Total equity | $4,400,000 |
>
> *Watch: the negative unit economics, the top-line decline, and how fast the
> equity cushion is drawn down if burn holds."*
>
> Follow-ups: "Drill into what's driving the operating burn?" · "Compare March
> with February?"

## Pitfalls

- **Don't divide money by 100.** Envelope `amount` is already dollars; a `cents`
  *unit label* still carries a major-units envelope — trust the helper, not the label.
- **Don't read `bps` as dollars.** `-3966` bps = −39.66% (divide by 100 for percent).
- **Don't invent a runway number.** The precomputed runway KPI is temporarily
  unavailable — report cash + burn and say so, rather than dividing to a month count.
- **Don't skip a tie-out.** The P&L, BS, and CF each carry their own reconciliation;
  check all three.
- **Don't add `compare`/`include_trend`** to corroboration pulls — they overflow
  and you don't need them; a single P&L `compare` is enough for a delta.
- **Don't sum single months** for the P&L/cash flow — use a wider period
  (`2025-Q1`) so flows aggregate correctly.
- **Flip the sign of equity/liabilities** when presenting to a human (they're
  carried negative); call a negative equity figure a *deficit* explicitly.
```
