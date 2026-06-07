---
name: explain-and-audit
description: >-
  Trace any reported financial number to its source and prove it, using the
  Lucid MCP connector's explain (7-part cell derivation) and drilldown (the
  real journal lines under a cell, split JE/AJE). Use this WHENEVER someone
  questions or wants to verify a figure from a Lucid report: "why is X this
  number", "explain this figure", "where does this come from", "what makes up
  <line>", "break down <number>", "show me the journal entries / transactions
  behind this", "drill down", "audit this", "reconcile", "tie this out", "is
  this right / prove it to me". This is the why-is-this-number-what-it-is and
  show-me-the-receipts skill. It builds on the mechanics in
  lucid:lucid-platform-guide (entity resolution, periods, views, the money
  envelope, tie-out checks) — defer to that for anything not specific to
  explain/drilldown.
---

# Explain & audit a Lucid number

Someone is staring at a number and doesn't trust it — or doesn't understand it.
Your job is to do what a controller does at sign-off: take that one cell, tell the
**story** of how it was built, show the **actual transactions** underneath, and
state plainly whether it **reconciles**. Two tools do this:

- **`explain`** — the *narrative*: the formula, which classifications matched,
  which accounts contributed, and which adjusting entries overlaid them.
- **`drilldown`** — the *receipts*: the real journal lines (ledger + adjustments),
  with a `sum_matches_cell` flag that is the audit guarantee.

Read `lucid:lucid-platform-guide` first if you haven't — this skill assumes you
already know how to resolve a company, pick a period/view, and read the money
envelope. Everything here is read-only.

## Target a cell precisely

Both tools point at **one cell**, identified by four coordinates:

| coordinate | what it is | how to get it |
|---|---|---|
| `report` | `tb` \| `bs` \| `pl` \| `cf_direct` \| `bva` \| `dashboard` | from what the user is looking at |
| `period` | `2025-03`, `FY2025`, `YTD@2025-03`, … | the report's primary period |
| `row` | the template **row_num** (e.g. the Gross Margin P&L row) | read it from the report response (`rows[]` carry `row_num` + `label`); maps in `lucid:lucid-platform-guide` → `reference/report-reference.md` |
| `column` | which money column on the row | see below |

`column` defaults to `amount`, which is right for P&L / BS / CF / dashboard. The
two reports with multiple columns need it set explicitly:

- **Trial balance:** `debit` \| `credit` \| `balance`
- **BVA:** `actual` \| `budget` \| `variance` (you can explain a *variance* — it
  derives the actual and budget legs)

**Get the row_num from the report response, don't guess it** — each report's
`rows[]` carry both `row_num` and `label`, so match on the label the user is
asking about. Row numbers are stable across periods for a given company/template
(that's the point) but are **per-company**, so don't hardcode them. The
most-asked cells: Revenues, COGS, Gross Margin, Total OpEx, Net Profit, EBITDA;
BS TOTAL ASSETS and Cash; CF Net operating and Total change. (Full maps live in
`lucid:lucid-platform-guide` → `reference/report-reference.md`.)

## The two-layer model — the key to every "why"

Lucid sits on **two layers**, and the gap between them is almost always the answer
to "why isn't this what I expected":

- **Ledger Layer** — the immutable lines straight from the ERP / accounting
  system. These never change. (`source: "ledger"`, the `base`/`erp_only` view.)
- **Controller Layer** — Lucid's own **adjusting journal entries (AJEs)** layered
  on at close: reclasses, deferrals, allocations. (`source: "aje"`, the `aje` view.)

The `lucid` view = **both layers netted**. So:

> A `lucid` number that surprises someone = the ledger figure **plus the
> adjustments**. `explain`/`drilldown` show you *exactly which* adjustments, line
> by line. That difference *is* the controller's work, and it's usually the story.

When someone asks "why is this different from what the bookkeeping shows", the
answer is: compare `base` to `lucid`, and the AJE lines are the difference.

## explain — the narrative (7 parts)

`explain(company, report, period, row, column="amount")` returns the full
derivation of the cell. The parts, and how to use each:

| part | contains | use it to say… |
|---|---|---|
| `scope` | `{report, row_num, label, column, amount}` | "This cell is **Gross Margin = −$50,000**." |
| `formula` | `{expression, narrative}` | "It's computed as **Revenues − COGS**." |
| `classifications` | `[{dimension, value}]`, dim ∈ `AW`\|`AX`\|`AY`\|`W`\|`BUDGET` | "It pulls every line classified **AW=Revenues** and **AW=COGS**." |
| `accounts` | `[{account_no, account_name, amount}]` | the contributing GL accounts and each one's signed contribution |
| `controller_entries` | the AJE overlay: `[{description, account_no, period, amount, rationale, state}]` | "Three approved AJEs adjusted it: …" (state is usually `approved`) |
| `journal_lines` | `[{account_no, account_name, period, net, source}]` | the per-account net, tagged `ledger` vs `aje` |
| `period_anchor` | `{opening_date, closing_date, opening_amount, closing_amount}` | for snapshots: where it started and ended |
| `version_trail` | `[{at, actor, event, description}]` | provenance: baseline classification, who touched it |

`explain` answers "**what is this made of**" at the account/adjustment grain
without leaving the report. It's the right first call: cheap, and it frames the
drilldown. Note `accounts` lists *signed contributions* — a credit account like
revenue shows **negative** (e.g. account 4000 "Product revenue"
contributing **−$250,000** to Gross Margin).

## drilldown — the receipts (real journal lines)

`drilldown(company, report, period, row, column="amount", view=…, limit=50,
je_cursor=…, aje_cursor=…)` returns the **actual journal lines** under the cell,
in **two parallel samples**:

- `je_lines` — Ledger Layer lines (`source: "ledger"`)
- `aje_lines` — Controller-Layer adjusting lines (`source: "aje"`)

Each line: `entry_date`, `entry_reference`, `entry_description`, `account_no` /
`account_name`, `counterparty`, `line_description`, `debit`, `credit`,
`net` (= debit − credit), `cf_line_class`. Plus the roll-ups:

- `je_total_sum` / `aje_total_sum`, `je_total_count` / `aje_total_count`
- `accounts_involved`
- `je_next_cursor` / `aje_next_cursor` — paginate each source **independently**
- **`sum_matches_cell`** — **the audit check** (below)

**The two sources net together.** An AJE can offset a ledger line — that's the
mechanism. In the worked Revenues example below, the ledger shows **+$100,000** but
an AJE reclasses the whole **−$100,000** away and a deferred-income cut-off AJE
nets **+$30,000** back, leaving the cell at **$30,000**. The ledger
alone would mislead; only JE **+** AJE is the true number.

### sum_matches_cell — never skip this

```
je_total_sum + aje_total_sum  ==  cell_value      ⟺   sum_matches_cell: true
```

This is the reconciliation guarantee: the lines you're showing actually add up to
the number being questioned. **If `sum_matches_cell` is `false`, say so loudly** —
something is unclassified or the books don't tie at the cell level, and the figure
is suspect. Don't present a clean explanation over a broken reconciliation.

### Pagination

`limit` is 1–200 per source (default 50). If `je_next_cursor` (or
`aje_next_cursor`) is non-null there are more lines on that side; pass it back as
`je_cursor` / `aje_cursor` to get the next page. **The two cursors are
independent** — you can exhaust ledger lines while still paging AJEs. For the
audit check, trust `je_total_sum` / `aje_total_sum` (full-population totals) over
the sampled lines you happened to pull.

### Non-English descriptions

Real Lucid data may carry `line_description` / `entry_description` /
`account_name` values in a **non-English language** (a company's books are kept in
whatever language the ERP uses). **Preserve any such label verbatim** — quote the
original text exactly as returned. You may add a short English gloss, but never
silently translate or drop the source string; it's the auditable reference.

## The workflow

1. **Identify the cell** — report, period, row_num (from the maps), column.
   Resolve the company handle first (`search_entities`) if you don't have it.
2. **`explain`** — get the story: formula, classifications, contributing
   accounts, controller adjustments.
3. **`drilldown`** — get the receipts: the JE and AJE lines; page if cursors are
   non-null.
4. **State the reconciliation** — `sum_matches_cell` (and, if relevant, the host
   report's own tie-out from the platform guide). Only then present the number.

Keep it to a few calls. `explain` + one `drilldown` answers most questions; add
pages only when the user wants every line. See `reference/audit-checklist.md` for
the exact checks to run before you call a number trustworthy.

## Output structure

Report an explanation in this order — story first, receipts second, verdict last:

1. **The figure** — the cell, its label, and value. "Gross Margin (the Gross
   Margin P&L row), Mar 2025, **lucid view: −$50,000**."
2. **The formula / story** — `formula.expression` in plain words, and which
   classifications feed it. "Revenues − COGS, over all AW=Revenues and AW=COGS
   lines."
3. **Contributing accounts & adjustments** — the material `accounts` (signed),
   then the `controller_entries`: what each AJE did and why it moved the number.
   "The ledger revenue was $100,000, but an approved AJE reclassed it out and a
   deferred-income cut-off AJE netted part of it back."
4. **Journal-line evidence** — the concrete JE / AJE lines from `drilldown`:
   dates, references, accounts, net amounts (labels preserved verbatim). The
   receipts.
5. **Reconciliation verdict** — `sum_matches_cell: true/false`, the JE and AJE
   totals, and whether the host report ties out. "JE +$100,000 and AJE −$70,000
   net to the $30,000 cell — **reconciled (sum_matches_cell: true)**."

State which **view** you used (`lucid` unless told otherwise) — the number is
meaningless without it.

## Worked examples — illustrative example, fictional company (Acme Inc.), synthetic figures

> These two examples use a **fictional company (Acme Inc., code `ACME`)** and
> **synthetic figures** for illustration only — they are not real Lucid data.
> The `row=` values below are placeholders: **always read the actual `row_num`
> from the report response** (`rows[]` carry `row_num` + `label`) rather than
> hardcoding — row numbers are per-company/per-template (see
> `lucid:lucid-platform-guide` → `reference/report-reference.md`).

### 1. "Why is Gross Margin negative?" — `explain(pl, 2025-03, Gross Margin row)`

`explain(company="ACME", report="pl", period="2025-03", row=<Gross Margin row_num>)`
returns:

- **scope:** Gross Margin = **−$50,000**.
- **formula:** `Revenues − COGS` — "revenue left after direct cost of goods sold."
- **classifications:** `AW=Revenues`, `AW=COGS`.
- **accounts:** 4000 "Product revenue" **−$250,000** (revenue, shown negative);
  5100 "Delivery salaries" **+$180,000**; 5200 "Hosting & infrastructure"
  **+$20,000** (the COGS lines, shown positive).
- **controller_entries (approved AJEs):** "Reclassify hosting costs from G&A to
  COGS" **+$35,000**; "Deferred-revenue cut-off adjustment" **−$30,000**.

**Story:** the negative margin is COGS (delivery salaries + allocated hosting)
exceeding the revenue that *survives* the controller adjustments — hosting is
pulled into COGS and a deferred-revenue cut-off reduces recognized revenue. The
AJEs are the why.

### 2. "Show me the transactions behind Revenues" — `drilldown(pl, 2025-03, Revenues row)`

`drilldown(company="ACME", report="pl", period="2025-03", row=<Revenues row_num>)`
returns the **Revenues** cell = **$30,000**, split:

- **je_total_sum: +$100,000** (1 ledger line): a customer invoice (reference
  `INV-1001`, account 4000 "Product revenue", debit/credit/net consistent, net
  +$100,000).
- **aje_total_sum: −$70,000** (2 AJE lines):
  - a revenue reclass, net **−$100,000**.
  - a deferred-income cut-off netting **+$30,000**, on account 4010 "Deferred
    revenue".
- **je_total_count: 1**, **aje_total_count: 2**, **accounts_involved: 2**.
- **sum_matches_cell: true** — $100,000 + (−$70,000) = **$30,000**. ✔

**Receipts + verdict:** one real invoice on the ledger, two adjusting lines that
reclass it and recognize the deferred portion; they reconcile exactly to the
reported cell. (If a real label came back in a non-English language, you would
quote it verbatim here.)

## Reference

- **`reference/audit-checklist.md`** — the concrete checks to run before you tell
  anyone a number is correct.
- **Row maps & response shapes** — `lucid:lucid-platform-guide` →
  `reference/report-reference.md`: which `row_num` is which line on every report,
  and the exact JSON shape of the `explain` / `drilldown` payloads.
