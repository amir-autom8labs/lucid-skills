---
name: board-pack
description: >-
  Assemble a board-/investor-ready financial package from the Lucid CFO
  connector — an executive narrative plus the standard exhibits (KPI scorecard,
  P&L with prior-period comparison, balance sheet, cash flow & runway, budget vs
  actual, risks/flags) — and export it to a document (xlsx workbook, PDF, or a
  slide deck). Use this WHENEVER someone wants to "build a board pack", "board
  deck", "board report" or "monthly board report", an "investor update", a "CFO
  report", to "prepare/package the financials for the board", or to "export the
  financials" / "build a financial package for <month or quarter>". This skill
  ORCHESTRATES the other Lucid skills: it pulls every statement for ONE company +
  period + view in a single coherent pass, cross-checks that the figures agree
  across statements, reconciles, and only then hands a clean tabular dataset to
  the document skills. Reach for it when the deliverable is a finished package,
  not a single answer.
---

# Building a board pack from Lucid

A board pack is not a pile of reports — it is **one coherent story** told in a
fixed order, where every number agrees with every other number. The whole reason
this skill exists is **consistency**: the cash on the KPI scorecard, the cash on
the balance sheet, and the closing cash on the cash-flow statement must be the
*same dollar*, and the net profit on the P&L must be the *same dollar* as the
current-year P&L line on the balance sheet. A board catches mismatches instantly
and it destroys trust. So your job is: pull everything for the **same company,
period, and view in one pass**, **reconcile** the cross-statement figures, then
structure and **export** — you do not free-style numbers and you do not let two
exhibits disagree.

Read `lucid:lucid-platform-guide` first for the mechanics (entity resolution,
period grammar, view modes, the money envelope, tie-out checks, payload-size
discipline). This skill assumes you know them and focuses on orchestration.

## What you are producing — the standard template

Always assemble these seven sections, in this order. The full skeleton with
field-level detail is in `assets/board-pack-template.md`; emit it in your chosen
document format.

1. **Executive summary** — 3–5 bullets a board actually cares about: cash
   position & runway, revenue and its trend, gross margin, the period's net
   result, and the single biggest risk or change. Plain language, numbers
   rounded sensibly, no jargon.
2. **KPI scorecard** — cash, runway, revenue (QTD), gross margin, straight from
   the dashboard. **Unit-aware** (cash = dollars, runway = months, gross margin =
   bps→percent). Show each KPI's comparator ("vs prior month / YoY").
3. **P&L** with a prior-period comparison column (MoM for a month, QoQ/YoY for a
   quarter). Headline rows only for the board (revenue, gross margin & %, OpEx,
   operating income, net profit, EBITDA); push the note-level detail to an
   appendix or omit.
4. **Balance sheet** — assets, liabilities, equity, **sign-flipped to positive
   magnitudes** for human reading (liabilities and equity arrive negative in
   Lucid's convention). Flag negative book equity explicitly if present.
5. **Cash flow & runway** — direct-method cash flow (operating / investing /
   financing nets, total change, opening & closing cash) plus the runway figure
   and the monthly burn behind it.
6. **Budget vs actual** — the material variances (top variances by magnitude),
   not every line. Lead with revenue and net-profit variance vs plan.
7. **Risks & flags** — any tie-out failure on ANY statement (surface it loudly),
   negative equity, short runway, large unexplained variances, or
   `9999/unclassified` cash-flow lines.

## The workflow

### 1. Resolve once, lock the parameters

Resolve the company to a real `code` (`search_entities`/`list_entities`). Then
**fix three parameters for the entire pack** and reuse them everywhere:

- `company` — one entity (or the root for a consolidated pack).
- `period` — one period string. A monthly board pack is usually the close month
  (e.g. `2025-03`); some boards want the quarter (`2025-Q1`). Pick one and state
  it. P&L / cash flow / BVA are flows over that period; balance sheet is the
  snapshot at its end.
- `view` — default `lucid` (close-ready, adjusted) unless asked otherwise. **Say
  which view the pack is on.** Mixing views across exhibits is how numbers stop
  agreeing — never do it.

If anything is ambiguous (which entity, which period, month vs quarter, which
view), ask once up front rather than producing a pack on the wrong basis.

### 2. Lean on the analysis skills — don't re-derive

You are an orchestrator. For each section's analysis, reuse the dedicated skill
rather than re-implementing its logic:

| Section | Skill to lean on |
|---|---|
| KPI scorecard, exec-summary framing | `lucid:financial-position-review` |
| P&L exhibit, margins | `lucid:pl-and-margin-analysis` |
| Cash flow & runway | `lucid:cash-and-runway` |
| Budget vs actual | `lucid:budget-vs-actual` |
| Balance sheet (sign-flip, liquidity) | `lucid:balance-sheet-review` |
| Any "why is this number" follow-up | `lucid:explain-and-audit` |

Compose their outputs into the template — the value you add is consistency,
ordering, and the export.

### 3. Pull compactly, all in one pass

Pull all five statements for the locked company/period/view: `get_dashboard`,
`get_pl`, `get_balance_sheet`, `get_cash_flow_direct`, `get_bva`. **Request only
what you need** — single period, headline + subtotal rows. The P&L wants a
prior-period column, so add `compare="mom"` (month) or `compare="qoq"`/`"yoy"`
(quarter) **on the P&L only**; that one report may exceed the result limit and
spill to a file — that's expected.

**Never paste giant raw JSON into context.** Use the shared helper / CLI to
extract compact tables, especially from spilled files:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/lucid_utils.py kpis   dashboard.json
python ${CLAUDE_PLUGIN_ROOT}/scripts/lucid_utils.py totals pl.json
python ${CLAUDE_PLUGIN_ROOT}/scripts/lucid_utils.py rows   pl.json --section summary --nonzero
python ${CLAUDE_PLUGIN_ROOT}/scripts/lucid_utils.py totals bs.json
python ${CLAUDE_PLUGIN_ROOT}/scripts/lucid_utils.py totals cf.json
python ${CLAUDE_PLUGIN_ROOT}/scripts/lucid_utils.py bva    bva.json --top 10
```

To produce the export-ready dataset in one shot, run the bundled assembler,
which reads the five payloads and emits a tidy, labelled multi-sheet
JSON/CSV bundle for the document skills to consume:

```bash
python ${CLAUDE_PLUGIN_ROOT}/skills/board-pack/scripts/board_pack.py \
  --dashboard dashboard.json --pl pl.json --bs bs.json \
  --cf cf.json --bva bva.json --format json
```

It does the unit-aware KPI parsing, the balance-sheet sign-flip, the variance
ranking, **and the cross-statement reconciliation** for you — so the workbook and
the narrative come from one source of truth.

### 4. Reconcile BEFORE you export — this is the point

Cross-check that the statements agree. The non-negotiable ties:

- **Cash** is one number everywhere:
  `dashboard cash KPI == balance sheet Cash row == cash flow closing_cash`.
- **Net result** is one number:
  `P&L Net Profit row == balance sheet Current-year P&L row`
  (note the balance-sheet sign convention — current-year P&L sits in equity as a
  credit, so a loss shows with the opposite sign; compare magnitudes/derivation,
  don't just compare raw signs).

> Row numbers/labels are configured per company; the example row indices below
> and in `scripts/board_pack.py` are defaults — verify against the foundation
> `reference/report-reference.md` and prefer the stable `totals.*` keys where
> available.
- **Every tie-out check passes**: P&L/BVA `check_delta == 0`, balance sheet
  `balance_check_delta == 0`, cash flow `tieout.period_delta == 0`, trial balance
  `balance_check_delta == 0`, dashboard `tie_out_ok == true`.

The assembler runs these and reports each as OK / MISMATCH. **If anything fails,
do not silently ship the pack** — fix the basis (wrong period? wrong view? a real
books problem?) or, if it's a genuine books issue, surface it prominently in
Section 7 (Risks & flags) and call it out in the exec summary. A board pack with
a quiet reconciliation hole is worse than no pack.

### 5. Export with the right document skill

The board-pack skill **gathers, reconciles, and structures**; it hands a clean,
tabular, labelled dataset to a document skill to render. Do **not** reimplement
xlsx/pdf/pptx generation here.

| Deliverable asked for | Skill to use |
|---|---|
| Workbook (one sheet per exhibit) | `document-skills:xlsx` |
| PDF report | `document-skills:pdf`, or `md-to-pdf` / `document-skills:md-to-pdf` from a markdown pack |
| Slide deck | `document-skills:pptx` |
| Markdown only | emit `assets/board-pack-template.md` filled in |

For a workbook, give the xlsx skill one sheet per exhibit (Summary, KPIs, P&L,
Balance Sheet, Cash Flow, BvA, Risks) with labelled columns; the assembler's
JSON/CSV output is already shaped for this. For a PDF, fill in the markdown
template and convert. Keep every figure traceable to the locked
company/period/view, which you should print on the cover/header of the pack.

## Constraints

- **Read-only.** You only read from Lucid; never imply you wrote anything back.
- **Few calls.** Five report pulls for one period is the budget; do not add
  `compare` beyond the single P&L comparison and **never** use
  `include_trend`/`include_composition` across the pack (overflow). Use the
  `lucid_utils` CLI on spilled files instead of re-pulling.
- **One basis.** Same company + period + view across all exhibits. State it.
- **Prefer validated numbers** and never present figures whose tie-out failed
  without flagging them.

## Worked example — Acme Inc., March 2025 (monthly pack, view `lucid`)

> *Illustrative example — fictional company (Acme Inc.), synthetic figures.*

Locked basis: `company` = Acme Inc. (code `ACME`), `period` = `2025-03` (P&L
comparison `mom`; quarter figures from `2025-Q1` where the board wants QTD),
`view` = `lucid`.

| Section | Figure | Value |
|---|---|---|
| KPI | Cash | **$8,000,000** |
| KPI | Runway | **14 mo** |
| KPI | Revenue (Q1) | **$250,000** |
| KPI | Gross margin | **−20.00%** (bps `-2000` ÷ 100) |
| P&L | Q1 Net profit | **−$880,000** |
| P&L | Q1 EBITDA | **−$890,000** |
| Cash flow | Total change in cash (Mar) | **−$480,000** |
| Balance sheet | Total assets | **$8,200,000** |
| Balance sheet | Total equity (magnitude) | **−$4,400,000** wire → **+$4.4M positive equity** (sign-flipped); eroding via accumulated losses — flag the trajectory |

**The consistency check (show this in the pack):**

```
Cash reconciliation — Mar 2025, view lucid
  Dashboard cash KPI .............. $8,000,000
  Balance sheet cash row .......... $8,000,000   ✓ agrees
  Cash flow closing_cash .......... $8,000,000   ✓ agrees
  → RECONCILED
```

All tie-outs OK for this period. The flags to carry into Section 7: gross margin
is deeply negative (−20.00%), the quarter ran a net loss of −$880,000, and book
equity — though still **positive at +$4.4M** — is being eroded by accumulated
losses. These are exactly the things a board will ask about, so lead with them in
the exec summary rather than burying them. (Sign-flip the wire equity before
presenting; don't mislabel the −$4,400,000 wire value as negative equity — it is
positive once flipped.)

## Files in this skill

- `assets/board-pack-template.md` — the fill-in section skeleton (also the
  markdown export source).
- `scripts/board_pack.py` — reads the five Lucid payloads and emits a tidy,
  labelled multi-sheet dataset (JSON or CSV) plus the cross-statement
  reconciliation, for the document skills to consume.
- `reference/assembly-checklist.md` — a one-page pre-flight / reconciliation
  checklist to run before exporting.
