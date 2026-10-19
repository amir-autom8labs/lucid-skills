---
name: board-pack
description: >-
  build-deliverable intent: assemble a FINISHED board-/investor-ready financial PACKAGE
  from the Lucid connector — an executive narrative plus the standard exhibits (KPI
  scorecard, P&L with comparison, balance sheet, cash flow & runway, budget vs actual,
  risks) — and EXPORT it to a document (PDF or slide deck). Use this WHENEVER the
  deliverable is a packaged artifact: "build a board pack / board deck / board report",
  "monthly board report", "investor update", "CFO report", "package the financials for
  the board", "export the financials", "financial package for {month}". It ORCHESTRATES
  one coherent pass across every statement, cross-checks that figures agree, reconciles,
  then hands a clean dataset to the document skills. Do NOT use it for a SINGLE question
  or one-statement analysis (the P&L, cash, balance sheet, budget, or the "how are we
  doing" review) → the matching analysis skill. Reach here only for a finished package.
---

# Building a board pack from Lucid

A board pack is not a pile of reports — it is **one coherent story** told in a
fixed order, where every number agrees with every other number. The whole reason
this skill exists is **consistency**: the cash on the balance sheet and the
closing cash on the cash-flow statement must be the
*same dollar*, and the net profit on the P&L must be the *same dollar* as the
current-year P&L line on the balance sheet. A board catches mismatches instantly
and it destroys trust. So your job is: pull everything for the **same company,
period, and view in one pass**, **reconcile** the cross-statement figures, then
structure and **export** — you do not free-style numbers and you do not let two
exhibits disagree.

The connector mechanics (entity resolution, period grammar, view modes, the
money envelope, tie-out checks) live in the tool docstrings and the system
prompt; this skill assumes them and focuses on orchestration.

## What you are producing — the standard template

Always assemble these seven sections, in this order. The full skeleton with
field-level detail is in `assets/board-pack-template.md`; emit it in your chosen
document format.

1. **Executive summary** — 3–5 bullets a board actually cares about: cash
   position and burn trajectory, revenue and its trend, gross margin, the period's
   net result, and the single biggest risk or change. Plain language, numbers
   rounded sensibly, no jargon.
2. **KPI scorecard** — one call: `get_status(company, period=…,
   sections=["kpis"])`, the backend-computed strip (cash · runway · revenue ·
   gross margin · operating profit · net profit · burn · revenue QTD), the same
   figures the CFO dashboard draws. Quote the cards verbatim and
   never re-derive one off a statement — two numbers for one month in one pack is
   the failure this exhibit used to have. Money arrives in major units; `runway`
   is **months** and `gross_margin` is **basis points**. A card whose `amount` is
   `null` is reported with its `comparator`'s reason, never as a zero, and a
   `provisional: true` month is labelled as not yet closed.
3. **P&L** with a prior-period comparison column (MoM for a month, QoQ/YoY for a
   quarter). Headline rows only for the board (revenue, gross margin & %, OpEx,
   operating income, net profit, EBITDA); push the note-level detail to an
   appendix or omit.
4. **Balance sheet** — assets, liabilities, equity, **sign-flipped to positive
   magnitudes** for human reading (liabilities and equity arrive negative in
   Lucid's convention). Flag negative book equity explicitly if present.
5. **Cash flow** — direct-method cash flow (operating / investing / financing
   nets, total change, opening & closing cash) and the monthly operating burn
   behind it. The **runway** comes from the KPI scorecard's own
   `runway` card, not from dividing the cash flow — report it beside the burn and
   never compute one yourself.
6. **Budget vs actual** — **temporarily unavailable.** `get_bva` returns a "not
   available yet" stub — do not call it for numbers; note that the BvA exhibit
   isn't available yet rather than presenting variances.
7. **Risks & flags** — any tie-out failure on ANY statement (surface it loudly),
   negative equity, a thin cash cushion, or a non-zero `unclassified` cash-flow row.

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

Pull the four statements for the locked company/period/view: `get_pl`,
`get_balance_sheet`, `get_cash_flow_direct`, `get_trial_balance`. **Request only
what you need** — single period, **`density=summary`** (the ~25 category rows with
their `row_num`s and the `totals` block, no note appendix; that's the headline +
subtotal detail a board wants). The P&L wants a prior-period column, so add
`compare="mom"` (month) or `compare="qoq"`/`"yoy"` (quarter) **on the P&L only**;
that one report (summary + compare) may still exceed the result limit and spill to
a file — that's expected.

> **The KPI scorecard is `get_status(sections=["kpis"])`, not `get_dashboard`**
> (which stays withdrawn) — one extra call, quoted verbatim. **Budget-vs-actual
> is still temporarily unavailable**: `get_bva` returns a "not available yet"
> stub, so do not call it for numbers; note that the BvA exhibit isn't available
> yet rather than presenting variances.

**Never paste giant raw JSON into context.** Use the shared helper / CLI (relative
paths from the skill dir) to extract compact tables, especially from spilled files:

```bash
python scripts/lucid_utils.py totals pl.json
python scripts/lucid_utils.py rows   pl.json --section summary --nonzero
python scripts/lucid_utils.py totals bs.json
python scripts/lucid_utils.py totals cf.json
```

To produce the export-ready dataset in one shot, run the bundled assembler,
which reads the statement payloads and emits a tidy, labelled multi-sheet
JSON/CSV bundle for the document skills to consume:

```bash
python scripts/board_pack.py \
  --pl pl.json --bs bs.json --cf cf.json --format json
```

It does the balance-sheet sign-flip **and the cross-statement reconciliation** for
you — so the exhibits and the narrative come from one source of truth. (The
assembler still accepts optional `--dashboard`/`--bva` inputs, but those tools are
withdrawn/stubbed — don't pass them.)

### 4. Reconcile BEFORE you export — this is the point

Cross-check that the statements agree. The non-negotiable ties:

- **Cash** is one number everywhere:
  `balance sheet totals.cash == cash flow closing_cash`.
- **Net result** is one number:
  `P&L Net Profit row == balance sheet Current-year P&L row`
  (note the balance-sheet sign convention — current-year P&L sits in equity as a
  credit, so a loss shows with the opposite sign; compare magnitudes/derivation,
  don't just compare raw signs).

> Row numbers/labels are configured per company; the example row indices below
> and in `scripts/board_pack.py` are defaults — verify against the foundation
> `reference/report-reference.md` and prefer the stable `totals.*` keys where
> available.
- **Every tie-out check passes**: P&L `check_delta == 0` (with
  `check_unresolved` empty — a `0` beside a non-empty list is an UNEVALUATED control,
  not a pass), balance sheet `balance_check_delta == 0` (with
  `balance_check_unresolved_roles` empty — same contract, different field name),
  cash flow `tieout.period_delta == 0`, trial balance `balance_check_delta == 0`.

The assembler runs these and reports each as **OK / MISMATCH / NOT EVALUATED**,
and `reconciliation.overall_ok` is three-valued to match: `true` (every present
control produced a reading and they all tie), `false` (something mismatched),
`null` (nothing mismatched, but at least one control could not be evaluated —
`reconciliation.unevaluated` names which). **Never read `null` as a pass.**

**If anything fails OR anything is unevaluated, do not silently ship the pack** —
fix the basis (wrong period? wrong view? a real books problem?) or, if it's a
genuine books issue, surface it prominently in Section 7 (Risks & flags) and call
it out in the exec summary. An unevaluated control is not a clean bill of health;
say the pack could not be reconciled and why. A board pack with a quiet
reconciliation hole is worse than no pack.

### 5. Export with the right document skill

The board-pack skill **gathers, reconciles, and structures**; it hands a clean,
tabular, labelled dataset to a document skill to render. Do **not** reimplement
pdf/pptx generation here.

| Deliverable asked for | Skill to use |
|---|---|
| Workbook / Excel | your environment's xlsx skill, if one is available; otherwise point out that each report in Lucid has an **Export** button that downloads it to Excel |
| PDF report | your environment's pdf skill, or convert the filled markdown pack |
| Slide deck | your environment's pptx skill |
| Markdown only | emit `assets/board-pack-template.md` filled in |

When no format is named, produce the markdown pack. For a PDF, fill in the
markdown template and convert. Keep every figure traceable to the locked
company/period/view, which you should print on the cover/header of the pack.

### 6. The chat message that accompanies the pack

Alongside the file, say what the pack contains and the headline story (cash and
burn, revenue trend, the period's result, the single biggest flag), and call out
any tie-out that failed. Any figure you repeat in chat is copied from the same
exhibit, so chat and pack can never disagree. Offer **2–3 follow-ups** (e.g. "Add
a QoQ revenue-bridge slide?", "Build the same pack for the prior month?").

## Constraints

- **Read-only.** You only read from Lucid; never imply you wrote anything back.
- **Few calls.** Four report pulls for one period is the budget; do not add
  `compare` beyond the single P&L comparison and **never** use
  `include_trend`/`include_composition` across the pack (overflow). Use the
  `lucid_utils` CLI on spilled files instead of re-pulling.
- **One basis.** Same company + period + view across all exhibits. State it.
- **Projections are disclosed.** If the pack's period is an open month, `lucid`
  figures include projected entries for recurring items not yet booked. Pass the
  same `include_projections` to every exhibit, and wherever a figure has a
  non-zero `projected` part, the narrative and the exhibit state it ("of which
  $310k projected"). Never present a projected figure as booked in a board
  pack; when the board wants booked numbers only, pass
  `include_projections=false` and say so.
- **Prefer validated numbers** and never present figures whose tie-out failed
  without flagging them.

## Worked example — Acme Inc., March 2025 (monthly pack, view `lucid`)

> *Illustrative example — fictional company (Acme Inc.), synthetic figures.*

Locked basis: `company` = Acme Inc. (code `ACME`), `period` = `2025-03` (P&L
comparison `mom`; quarter figures from `2025-Q1` where the board wants QTD),
`view` = `lucid`.

| Section | Figure | Value |
|---|---|---|
| Cash (BS `totals.cash`) | Cash | **$8,000,000** |
| KPI scorecard | Runway (`get_status` `kpis`) | **18 months** (quoted, not divided) |
| P&L | Revenue (Q1) | **$250,000** |
| P&L | Gross margin (Q1) | **−20.00%** |
| P&L | Q1 Net profit | **−$880,000** |
| P&L | Q1 EBITDA | **−$890,000** |
| Cash flow | Total change in cash (Mar) | **−$480,000** |
| Balance sheet | Total assets | **$8,200,000** |
| Balance sheet | Total equity (magnitude) | **−$4,400,000** wire → **+$4.4M positive equity** (sign-flipped); eroding via accumulated losses — flag the trajectory |

**The consistency check (show this in the pack):**

```
Cash reconciliation — Mar 2025, view lucid
  Balance sheet cash figure ....... $8,000,000
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
- `scripts/board_pack.py` — reads the statement payloads and emits a tidy,
  labelled multi-sheet dataset (JSON or CSV) plus the cross-statement
  reconciliation, for the document skills to consume. (It still tolerates optional
  `--dashboard`/`--bva` inputs for when those tools return, but they're withdrawn
  /stubbed today — don't pass them.)
- `reference/assembly-checklist.md` — a one-page pre-flight / reconciliation
  checklist to run before exporting.
