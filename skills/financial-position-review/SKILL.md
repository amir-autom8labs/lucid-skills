---
name: financial-position-review
description: >-
  The monthly-close / "how are we doing" snapshot for a company on the Lucid
  CFO connector. Dashboard-led, cross-statement health check: pull the
  dashboard, then corroborate against P&L, balance-sheet, and cash-flow totals,
  verify EVERY report's tie-out, and produce a tight CFO-grade summary
  (position, profitability, liquidity, cash trajectory, risks) citing real
  figures. USE THIS WHENEVER someone wants the overall state of the business
  rather than one statement — phrasings like "how are we doing", "monthly
  review", "close review", "financial health", "give me the state of the
  business", "where do we stand", "month-end summary", or "snapshot of
  <company> for <month>". When the ask is scoped to one statement (just P&L,
  just cash, just budget), prefer the focused skill instead. Reads from the
  read-only Lucid MCP connector; builds on lucid:lucid-platform-guide.
---

# Financial position review (the close snapshot)

This is the **"how are we doing" answer**: not one statement, but a single
coherent read across all of them. A CFO closing the month wants four things at
once — where do we *stand* (position), are we *making money* (profitability),
can we *pay our bills* (liquidity), and where is *cash heading* (trajectory) —
plus an honest list of risks. Your job is to assemble that from the dashboard
and the three core statements, **prove each one ties out**, and write it up so a
busy executive trusts it at a glance.

> Read **`lucid:lucid-platform-guide` first** for the mechanics this skill
> assumes: entity resolution, period grammar (`2025-03`, `FY2025`, `YTD@…`),
> view modes (`base`/`aje`/`lucid`), the money envelope, and comparison gating.
> This skill does **not** repeat them. It *does* restate two things — tie-out
> discipline and compact retrieval — because they are the spine of a review.

## Why dashboard-led

The dashboard is the only Lucid call that pre-bundles the headline KPIs (cash,
runway, revenue QTD, gross margin), the OpEx mix, and a one-shot `tie_out_ok`
flag. It's the fastest way to *frame* the month. But a dashboard is a summary —
you still **corroborate it against the underlying statements** so the story
holds up: the dashboard's gross-margin % should be reflected in the P&L, its
cash delta should equal the cash-flow `total_change`, and its tie-out flag is
one of four you must check, not a substitute for the rest.

So the shape of a review is: **dashboard to frame → P&L / BS / CF to corroborate
→ tie-out on all four → write up.**

## Tie-out discipline (non-negotiable here)

A position review that quietly presents a number from books that don't reconcile
is worse than no review. **Check every report's reconciliation before you trust
a single figure**, and surface the result explicitly — your summary must carry a
literal `Tie-out: OK` / `Tie-out: OFF` line.

| Report | Check field | Tied out when |
|---|---|---|
| Dashboard | `tie_out_ok` | `true` |
| P&L | `totals.check_delta` | `= 0` |
| Balance sheet | `totals.balance_check_delta` | `= 0` |
| Cash flow | `tieout.period_delta` | `= 0` |

If **any** is off, say so prominently at the top, name which report, and treat
its figures as provisional. One OFF report taints the whole snapshot's
credibility — don't bury it.

## Compact retrieval (don't blow up context)

These reports are large (a P&L is ~170 rows). For a review you only need the
**`totals` block and a handful of subtotal rows** — never the leaf detail. So:

- Pull **one period, one view, no extras.** Do **not** pass `compare` /
  `include_trend` / `include_composition` — they multiply the payload and can
  overflow the tool result. The dashboard already gives you trend context
  (deltas + sparklines) for free.
- If a tool result **spills to a file**, do not read the raw JSON back. Run the
  shared helper or `position_review.py` against the file path instead.

## The worked flow — company ACME, 2025-03, view `lucid`

> **Illustrative example — fictional company (Acme Inc.), synthetic figures.**
> All numbers below are made up and internally consistent for teaching; they are
> not real client data.

### 1. Resolve and frame with the dashboard

```text
search_entities("Acme") → code "ACME"        # never guess a handle
get_dashboard(company="ACME", period="2025-03", view="lucid")
```

Read it through the unit-aware helper so you don't misread the mixed units
(`bps` is basis-points×100 → divide by 100 for %; `months` is an int; `cents`
unit actually carries a **major-units** money envelope — **never divide by
100**):

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/lucid_utils.py kpis dashboard.json
```

For Acme Inc. / Mar 2025 this frames the month:

| KPI | Value | vs |
|---|---|---|
| Cash | **$8,000,000** | −$480,000 vs Feb 2025 |
| Runway | **14 mo** | at current burn |
| Revenue QTD | **$250,000** | −40% YoY (vs Q1 2024) |
| Gross margin | **−20.00%** | −8.0pp vs Feb 2025 |

OpEx donut: R&D $400,000 · S&M $300,000 · G&A $150,000 = **$850,000 total**.
`tie_out_ok: true`. So the frame is: well-capitalized (14mo runway) but revenue
has collapsed YoY and gross margin is *negative* — selling below cost. That's
the thread to pull on in the statements.

### 2. Corroborate against the three statements

Pull each as a **single period, no extras**, and save to files:

```text
get_pl(company="ACME", period="2025-Q1", view="lucid")          → pl.json
get_balance_sheet(company="ACME", period="2025-03", view="lucid") → bs.json
get_cash_flow_direct(company="ACME", period="2025-03", view="lucid") → cf.json
```

> Period note: the dashboard's revenue/margin KPIs are **quarter-to-date**, so
> pull the P&L for `2025-Q1` to corroborate them on the same basis; balance
> sheet and cash flow are read at/through the month `2025-03`.

Pull just the totals + tie-out from each spilled file:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/lucid_utils.py totals pl.json
python ${CLAUDE_PLUGIN_ROOT}/scripts/lucid_utils.py totals bs.json
python ${CLAUDE_PLUGIN_ROOT}/scripts/lucid_utils.py totals cf.json
```

Validated figures for Acme Inc. (synthetic):

- **P&L (Q1-2025):** net_profit **−$880,000**, gross_margin **−$50,000**,
  ebitda **−$890,000**, `check_delta $0`. → confirms the dashboard's negative
  gross margin; the quarter is deeply loss-making.
- **Balance sheet (Mar 2025):** total_assets **$8,200,000**, total_equity
  **−$4,400,000** wire → **+$4.4M positive equity** once sign-flipped
  (assets $8.2M = liabilities $3.8M + equity $4.4M), `balance_check_delta $0`. →
  assets are almost entirely the cash pile; equity is positive but being eroded
  by accumulated losses (~$15.0M paid-in vs ~$10.6M cumulative losses).
- **Cash flow (Mar 2025):** net_operating **−$450,000**, net_investing
  **−$30,000**, total_change **−$480,000**, `tieout.period_delta $0`. → the
  −$480,000 here **equals the dashboard's cash delta** — corroboration
  achieved. Burn is operating, not investing.

### 3. Verify all four tie-outs at once

`position_review.py` consolidates the snapshot and, most importantly, lays the
four reconciliations side by side so nothing slips through:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/financial-position-review/scripts/position_review.py \
    --dashboard dashboard.json --pl pl.json --bs bs.json --cf cf.json
```

All four read `OK` (delta $0 / `true`) for Acme Mar 2025 → the snapshot is
trustworthy. Had any read `OFF`, the script flags `OVERALL: OFF` and you lead
your write-up with that.

> **Row-number caveat.** `position_review.py` reads named totals by *row number*
> (e.g. P&L revenue at row 5). Row numbers and labels are **configured per
> company**, so don't treat any specific row index as universal — confirm them
> against the actual response and the foundation guide's
> `reference/report-reference.md` before relying on them.

### 4. Write it up

Map the corroborated figures into the output template below. Lead with the
tie-out line, then position → profitability → liquidity & cash → risks.

## Output structure

Produce a compact, scannable summary in this order. Always cite **real figures**
(from the helper, never re-keyed by hand), state the **view and period**, and
include the explicit tie-out line.

```text
## <Company> — Financial position, <Period> (view: lucid)
Tie-out: OK   (dashboard ✓ · P&L ✓ · balance sheet ✓ · cash flow ✓)
            └─ if any OFF: "Tie-out: OFF — <report> delta <$X>; figures provisional"

**Headline.** One or two sentences: the state of the business in plain terms.
e.g. "Well-capitalized — $8.0M cash, 14 months runway — but revenue has
collapsed (−40% YoY) and the business is selling below cost (gross margin
−20.0%), burning ~$0.5M/mo."

**Profitability.** Revenue $X (Δ YoY), gross margin $X / %, operating income $X,
EBITDA $X, net profit/(loss) $X. Name the driver of the result.

**Liquidity & cash.** Cash $X (Δ vs prior month), runway X mo at current burn,
total assets $X, total equity $X (sign-flip the wire value; only call it a
*deficit* if the flipped figure is negative). Where cash went this month:
operating $X / investing $X / financing $X.

**Risks & flags.** The 2–4 things that actually matter: negative gross margin,
revenue decline, eroding/deficit equity, runway threshold, any OFF tie-out, any
unexpected sign. Be direct; this is the part a CFO acts on.
```

### Worked example output (Acme Inc., 2025-03)

**Illustrative example — fictional company (Acme Inc.), synthetic figures.**

```text
## Acme Inc. — Financial position, Mar 2025 (view: lucid)
Tie-out: OK   (dashboard ✓ · P&L ✓ · balance sheet ✓ · cash flow ✓)

**Headline.** Well-funded but unprofitable. $8.0M cash and ~14 months of
runway, but Q1 revenue is only $250K (−40% YoY) and gross margin is negative
(−20.0%) — the company is selling below cost while carrying a full opex base.

**Profitability (Q1-2025).** Revenue $250,000 (−40% YoY). Gross margin
−$50,000 (−20.0%). OpEx $850,000 (R&D $400,000 · S&M $300,000 · G&A $150,000).
EBITDA −$890,000. Net loss −$880,000.

**Liquidity & cash (Mar 2025).** Cash $8,000,000, down $480,000 on the month;
runway 14 mo at current burn. Total assets $8,200,000 (almost entirely cash).
Total equity +$4.4M (positive), but eroding — ~$10.6M accumulated losses against
~$15.0M paid-in capital. Cash use this month was operating (−$450,000) plus modest
investing (−$30,000); no financing inflow.

**Risks & flags.**
- Negative gross margin (−20.0%, worsening 8.0pp MoM) — unit economics are upside-down.
- Revenue down 40% YoY — top line has fallen off, not a margin-only problem.
- Equity still positive ($4.4M) but eroding ~$0.9M/quarter at the current loss rate.
- Runway 14 mo is comfortable today but shrinks fast if burn holds and revenue doesn't recover.
```

## Pitfalls

- **Don't divide money by 100.** Envelope `amount` is already dollars. The
  dashboard's `cents` *unit label* still carries a major-units envelope — the
  helper handles it; trust the helper, not the label.
- **Don't read `bps`/`months` as dollars.** `-3966` bps = −39.66%; runway `17`
  is months. Use `kpi_view` / the `kpis` CLI.
- **Don't skip a tie-out** because the dashboard said `true`. The dashboard flag
  covers the dashboard; the P&L, BS, and CF each carry their own.
- **Don't add `compare`/`include_trend`** to corroboration pulls — they overflow
  and you don't need them; the dashboard already supplies trend context.
- **Don't sum single months** for the P&L/cash flow — use a wider period
  (`2025-Q1`) so flows aggregate correctly.
- **Flip the sign of equity/liabilities** when presenting to a human (they're
  carried negative); call a negative equity figure a *deficit* explicitly.
```
