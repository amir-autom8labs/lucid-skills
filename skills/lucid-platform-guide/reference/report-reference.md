# Lucid report reference — row maps & response shapes

The exact JSON shape of every tool response, plus one company's report layout as
an illustration. All money fields are the envelope
`{"amount": "1234.56", "currency": "USD", "units": "major"}` unless noted.

> ## Read a line by its IDENTITY. Never by its row number.
>
> `row_num` is a **coordinate, not a name.** Every P&L band is elastic — one row
> per operating-expense function the company routes — so a company with five
> expense functions instead of three pushes every row below that band down by
> two. On the Balance Sheet the asset rows come out in whatever order that
> company's chart produced, so row 5 is whichever asset came first, not
> necessarily cash.
>
> This is not a rare edge case; it is what most companies look like. A number read by position is a real figure from the wrong
> line, and nothing about it looks wrong.
>
> **The order to reach for a figure, best first:**
>
> 1. **`totals`** — the headline block (`totals.net_profit`, `totals.revenues`,
>    `totals.total_assets`, `totals.closing_cash_end`, ...). Computed once in the
>    backend; quote it verbatim. Survives `density="totals"`, so it is also the
>    cheapest.
> 2. **`role`** — the stable name of a computed / scaffold row: P&L
>    `net_profit`, `ebitda`, `gross_margin`, `total_opex`, `operating_income`,
>    `income_before_tax`, `taxes`; Balance Sheet `total_assets`,
>    `total_current_assets`, `total_current_liabilities`,
>    `total_long_term_liabilities`, `total_liabilities`, `total_equity`,
>    `pl_loss_profit`, `total_liabilities_equity`, `check`.
> 3. **`heading_key`** — a headline bucket (`revenues`, `cost_of_sales`). OPEN
>    vocabulary: a company may mint its own heading, so handle an unfamiliar one
>    rather than rejecting it.
> 4. **`band_key`** — CLOSED arithmetic: which subtotal a row foots into
>    (`revenues`, `cost_of_sales`, `operating_expenses`,
>    `finance_expenses_income`, `other_expenses_income`, `tax_expenses`,
>    `equity_in_earnings_of_subsidiary`). A band holds SEVERAL rows, so it names
>    a set — map over it, and never assume how many members it has.
>
> A row is identified by `(band_key, heading_key, label)` — never by one of them
> alone, and never by `row_num`.
>
> **Cash is the one exception, and it is not a row.** `get_balance_sheet`'s
> `totals.cash` block carries the statement's cash figure: the balance of the
> accounts ticked as cash, counted per account wherever the statement presents
> them — `amount`, `components` (where those accounts are presented),
> `row_nums` (the rows of the cash classes), an `unresolved_reason` and any
> `disclosures`. Read `amount` verbatim and NEVER re-sum `row_nums` or
> `components`. `unresolved_reason` non-null ⇒ `amount` is null and there is
> no cash figure: quote the reason, never print `0`. `disclosures` non-empty ⇒
> the figure stands and differs from the statement's cash lines: part of it is
> presented outside a cash class ("includes …"), or a cash class also holds
> accounts that are not cash ("excludes …") — **show every clause beside the
> number**. An "includes" clause comes with the reconciliation from
> `components` ("of which $X presented under <class>"); an "excludes" clause
> has no amount on the wire and is shown on its own.
> The block survives `density="totals"`, so a cash question needs only that.
>
> **Every OTHER leaf has no identity on the wire — say so, do not substitute a
> number.** Receivables, payables, deferred income, share capital, retained
> earnings and intercompany carry no semantic identity: a BS detail
> row's label is the company's own `main_class` verbatim, so nothing tells you
> which of *their* mains means "accounts receivable". Report "not identified".
> A `0` is indistinguishable from a measured zero and reads as a finding.
>
> **Where `row_num` IS legitimate:** as a sort key for presentation order, and
> to target `explain` / `drilldown` using a `row_num` you read out of the very
> response you are holding. A coordinate that never outlives its own payload is
> fine. A coordinate copied from this document into your reasoning is not.
>
> The maps below are **one company's layout**, kept because they orient you to
> what a statement contains. They are not a lookup table.

## Contents
1. [Common envelopes](#common-envelopes)
2. [Dashboard](#dashboard)
3. [P&L](#pl)
4. [Balance sheet](#balance-sheet)
5. [Trial balance](#trial-balance)
6. [Cash flow (direct)](#cash-flow-direct)
7. [Budget vs Actual](#bva)
8. [explain](#explain)
9. [drilldown](#drilldown)
10. [Sign conventions](#sign-conventions)

---

## Common envelopes

Every report response ends with:
```json
"view": "lucid",
"period": {"kind": "month", "start": "2025-03-01", "end": "2025-03-31", "label": "Mar 2025"},
"generated_at": "2026-..."
```
`period.kind` ∈ `month|quarter|half|fy|ytd|r12|custom`. Multi-period rows carry a
`series` array (aligned to the requested `periods`/`compare` order — **not**
labelled) and, with `include_trend`, a 12-element `trend`. `fy_ytd` is the
fiscal-YTD value of the row.

---

## Headline KPIs — `get_status(sections=["kpis"])`
The precomputed CFO-home KPI bundle is served by **`get_status`**, not by a
report tool (the old `get_dashboard` is withdrawn). Ask for it
by name — it is **opt-in**, so a plain `get_status` call does not carry it:

`get_status(company, period="YYYY-MM", sections=["kpis"])` → one ordered list of
cards for **cash · runway · revenue · gross margin · operating profit · net
profit · burn · revenue QTD**, each with `amount`, `comparator`, `delta`, a
12-point `sparkline`, `provisional` and `polarity`. They are the same numbers the
dashboard draws, computed once in the backend — quote them, never re-derive them.

Three unit traps, all decided by the card's own `unit`: money cards arrive as
labelled major-unit envelopes (**never divide by 100**); `runway` is **months**
and `gross_margin` is **basis points** (1% = 100), both plain numbers. And
`amount: null` never means zero — it means the figure could not be identified,
with `comparator` carrying the reason.

Add `sections=["kpis", "moved"]` for the month's largest changes (P5), which the
same call serves. The OpEx mix and the tie-out flag are not on this bundle: read
the mix from the P&L and the tie-out from `get_status`'s `health` section.

---

## P&L
`get_pl(...)`. `rows[]`: `{row_num, label, section, is_subtotal, role, heading_key, band_key, parent_row_num, parent_identity, uncomputed, amount, series, trend, fy_ytd}`.
The identity fields (`role` / `heading_key` / `band_key` / `parent_identity`) are dropped from the wire when null — absent means "this row has none", so bind to whichever one a row does carry. `uncomputed` follows the same rule and is likewise absent unless true — it is a caveat about the money columns, not an identity.
`section` ∈ `summary` | `note` (expandable detail). Read `section` off the row — the row_num ranges that happen to separate them differ per company.

**Headline rows (section `summary`).** Bind to the **identity** column. The
`row_num` column is this one company's layout, shown so the shape is legible —
on a company with five operating-expense functions every row from
`total_opex` down sits two numbers lower.

| identity | line | row_num *(this company only)* |
|---|---|---|
| `heading_key: revenues` | Revenues | 5 |
| `heading_key: cost_of_sales` | COGS | 6 |
| **`role: gross_margin`** | **Gross Margin** (subtotal) | 7 |
| `band_key: operating_expenses` | R&D / S&M / G&A — **one row per routed function, count varies** | 10 / 11 / 12 |
| **`role: total_opex`** | **Total operating expenses** (subtotal) | 13 |
| **`role: operating_income`** | **Operating income / (Loss)** (subtotal) | 15 |
| `band_key: finance_expenses_income` / `other_expenses_income` | Financial / Other expenses (income) | 17 / 18 |
| **`role: income_before_tax`** | **Income (Loss) before tax** (subtotal) | 19 |
| `role: taxes` | Taxes on income | 21 |
| `role: equity_earnings` *(absent on generated templates)* | Equity in Earnings of Subsidiary | 22 |
| **`role: net_profit`** | **Net Profit / (Loss)** (subtotal) | 24 |
| **`role: ebitda`** | **EBITDA** (subtotal) | 30 |

`get_pl` and `get_consolidated_report` do not return % Gross Margin, Adjusted Net
Profit, Total expenses or Depreciation; the P&L and consolidated P&L do not display
them. The P&L carries no gross-margin percentage.

**`uncomputed: true`** marks a row the backend does not compute at all. Its
`amount` / `series` / `trend` / `fy_ytd` are structural zeros, never
measurements — never state, quote or chart one, not as a percentage and not as
zero. Different from
`totals.unresolved_roles`, which names a subtotal the template stamped on no
row and is repaired by re-provisioning; re-provisioning changes nothing here.

Notes (detail): one block per headline bucket — Revenues, COGS, each expense
function, Financial, Other, Taxes. Their row ranges are **entirely
company-specific** (they scale with how many accounts each note holds), so
select a note's leaves by `parent_identity` / `parent_row_num` — the structural
link the wire already carries from a leaf to the line it backs — never by a
range. On the reference chart they happened to fall at 35–53, 58–84, 86–106,
109–137, 140–175, 178–191, 194–198 and 201–208; on any other chart those numbers
mean nothing.

**`totals`:** `{revenues, gross_margin, operating_income, ebitda, net_profit, ledger_net_profit,
check_delta, check_unresolved, series_check_delta}`.
Tied out when `check_delta == 0` **and** `check_unresolved` is empty. `ledger_net_profit` is Net
Profit summed straight off the classified ledger (per routed `main_class`), `net_profit` is what the
template published, and `check_delta` is `ledger_net_profit − net_profit`. `check_unresolved` is a
list of reason strings: when it is non-empty an operand could not be resolved and the `0` is a
placeholder, not a tie-out — say "not evaluated, and here is why", never "the P&L ties out".

---

## Balance sheet
`get_balance_sheet(...)`. `rows[]`: `{row_num, label, section, is_subtotal, role, heading_key, is_header, is_residual, parent_row_num, parent_identity, amount, series, trend, fy_ytd}`.
As on the P&L, the identity fields are dropped when null.
`section` ∈ `assets | liabilities | equity | note | check`.

Bind to the **identity** column. Rows with **no identity** are account-level
leaves — you cannot name them on the wire, so report them as *not identified*
rather than reading the `row_num` beside them. The `row_num` column is one
company's ordering; another company's routing orders its assets differently, so
row 5 there is a different line entirely.

| identity | line | row_num *(this company only)* |
|---|---|---|
| **`totals.cash`** (not a row identity — see below) | Cash and Cash equivalents | 5 |
| *(none — leaf)* | Restricted Cash and Deposits | 6 |
| *(none — leaf)* | Short term deposits | 7 |
| *(none — leaf)* | Accounts Receivable | 8 |
| *(none — leaf)* | Other receivable | 11 |
| *(none — leaf)* | Intercompany (one row per related entity) | 12–14 |
| **`role: total_current_assets`** | **Total Current Assets** | 16 |
| *(none — leaf)* | Fixed assets / Accumulated depreciation | 19 / 20 |
| *(none — leaf)* | Lease right-of-use assets | 22 |
| **`role: total_assets`** | **TOTAL ASSETS** | 24 |
| *(none — leaf)* | Credit cards B.S | 27 |
| *(none — leaf)* | Accounts Payable | 29 |
| *(none — leaf)* | Deferred Income | 32 |
| *(none — leaf)* | Other current liabilities | 33 |
| **`role: total_current_liabilities`** | **Total Current Liabilities** | 35 |
| *(none — leaf)* | SAFE | 39 |
| **`role: total_long_term_liabilities`** | **Total Long-Term Liabilities** | 44 |
| **`role: total_liabilities`** | **Total liabilities** | 45 |
| *(none — leaf)* | Share capital | 46 |
| *(none — leaf)* | Add'l Paid-in Capital | 51 |
| **`role: pl_loss_profit`** | **Current-year P&L Loss (Profit)** | 55 |
| *(none — leaf)* | Retained earnings | 56 |
| **`role: total_equity`** | **Total Equity** | 57 |
| **`role: total_liabilities_equity`** | **TOTAL LIABILITIES & EQUITY** | 59 |
| **`role: check`** | check (should be 0) | 60 |
| *(none — note leaves; use `parent_row_num`)* | Notes 1–2 (Other receivable / Other current liabilities detail) | 66–84 |

**`totals`:** `{total_assets, total_liabilities, total_equity, balance_check_delta,
balance_check_unresolved_roles, unplaced_mains, series_check_delta, cash}`.

**`totals.cash`** = `{amount, series, row_nums, components, unresolved_reason,
disclosures}` — the statement's own cash figure, and the ONLY way to reach cash
from this payload (a BS cash row is an ordinary leaf with no `role` and no cash
band, so a `row_num` names whichever asset the tenant's routing ordered first).
Cash is the balance of the accounts ticked as cash, counted per account, so it
is not in general the sum of any rows. Render `amount` verbatim; never re-sum
`row_nums` or `components`. `series` is `amount` per period on a multi-period
call. `components[]` = `{main_class, row_nums, amount, whole, cash_class,
accounts[]}`, summing to `amount`: `cash_class: false` ⇒ cash presented under
another class (or, with `main_class: null`, on no Balance Sheet row), and
`accounts[]` (`account_no`, `name`, `amount`) lists those accounts that have a
balance; `whole: false` ⇒ the class also holds accounts that are not cash.
`row_nums` are the cash classes' rows and add up to `amount` only when every
component is `whole`. `unresolved_reason` non-null ⇒ `amount` is null: quote the
reason, never `0`. `disclosures` non-empty ⇒ one clause per component outside a
cash class ("includes N account(s) presented under <class>" / "… on no Balance
Sheet row"), and one per cash class whose accounts that are not cash hold a
non-zero total ("excludes N account(s) in <class> not ticked as cash") — show
every clause beside the figure. Survives `density="totals"`.

The `bs_cash_vs_cf_closing` control (`get_status` / `get_close_readiness`)
compares `totals.cash.amount` with the direct cash flow's closing cash. Both
count the same ticked accounts, so it does not test which accounts are cash;
it breaks when the classified cash walk does not equal those accounts'
movement, when an adjusting entry dated before the fiscal year sits on a cash
account, or when one account is ticked both cash and credit card.
Tied out when `balance_check_delta == 0` (i.e. `total_assets + total_liabilities + total_equity == 0`,
given the sign convention below).

---

## Trial balance
`get_trial_balance(...)`. Views are `erp_only | lucid`. `rows[]`:
`{account_no, account_name, debit_total, credit_total, balance, class, series, trend, fy_ytd}`.
`class` ∈ `A|L|E|R|X` (Asset/Liability/Equity/Revenue/eXpense; X = unknown default).
`balance` is signed: **+ = debit balance** (asset/expense), **− = credit balance**
(liability/equity/revenue).

**`totals`:** `{debit, credit, balance_check_delta, series_check_delta}`.
Tied out when `balance_check_delta == 0` (Σdebit − Σcredit).

---

## Cash flow (direct)
`get_cash_flow_direct(...)`. `rows[]`:
`{row_num, label, section, row_type, parent, group_key, is_subtotal, amount, ...}`.
`section` ∈ `operating | investing | financing | meta | breakdown | other`.
`row_type` ∈ `header | detail_cf_class | detail_tb_ay | ref | subtotal | net_section | grand_total | opening_cash | closing_cash | check | other_formula | unclassified`.

| row | line |
|---|---|
| 6 | Collection from customers |
| 8–18 | Operating cash out (COGS/R&D/S&M/G&A/Financial/Other/Tax/Payroll/VAT…) |
| 19 | Total expenses paid in cash (subtotal) |
| **21** | **Net cash — operating** (net_section) |
| 24–30 | Investing detail |
| **31** | **Net cash — investing** (net_section) |
| 34–38 | Financing detail (loans, options, SAFE, equity) |
| **39** | **Net cash — financing** (net_section) |
| **41** | **Total increase/(decrease) in cash** (grand_total) |
| 43 | Cash at beginning of period (opening_cash) |
| 44 | Cash at end of period (closing_cash) |
| 45 | Check (should be 0) |
| 62+ | Breakdown notes (per-category detail; rows linked via `parent`/`group_key`) |

The `ref` rows (8–13) total their note breakdown via `group_key`. A row_num
a row with `row_type` `unclassified` (label "Unclassified") is always present — non-zero there means lines fell
outside the classification map.

**`totals`:** `{net_operating, net_investing, net_financing, total_change, opening_cash_start, closing_cash_end, series_check_delta}`.
**`tieout`:** `{per_month: [{month, classified, bank_delta, delta}], classified_total, bank_delta_total, period_delta}`.
Tied out when `period_delta == 0` (classified cash flow == actual bank-balance change).

---

## BVA — temporarily unavailable
`get_bva(...)` currently returns a "budget-vs-actual is not available yet" stub;
relay that rather than presenting variance numbers. The shape below is retained
for when it is re-enabled. Same row skeleton as P&L (`section` ∈ `summary | note`), but each
row carries `{actual, budget, variance, variance_pct}` instead of a single
`amount`. `view` applies to `actual` only; `budget` is view-invariant.
`variance = actual − budget`; `variance_pct = variance / |budget|` (a float, or
`null` when `budget == 0`). Read row numbers from the [P&L map](#pl).

**`totals`:** `revenues_*`, `operating_income_*`, `net_profit_*`,
`total_expenses_*` (each as `_actual`/`_budget`/`_variance`) + `check_delta`.

---

## explain
`explain(company, report, period, row, column="amount")`. `report` ∈
`tb|bs|pl|cf_direct|bva|dashboard`. `column`: TB `debit|credit|balance`;
BVA `actual|budget|variance`; others `amount`. Returns the 7-part derivation:

```
scope:            {report, row_num, label, column, amount}
formula:          {expression, narrative}
classifications:  [{dimension(AW|AX|AY|W|BUDGET), value}]
accounts:         [{account_no, account_name, amount}]          # contributing accounts
controller_entries:[{entry_id, description, account_no, period, amount, rationale, state}]  # the AJE overlay
journal_lines:    [{account_no, account_name, period, net, source}]
period_anchor:    {opening_date, closing_date, opening_amount, closing_amount}
version_trail:    [{at, actor, event, description}]
```
Use it to answer "what is this number made of / which classifications and
adjustments produced it" without leaving the report grain.

## drilldown
`drilldown(company, report, period, row, column="amount", view=…, limit=50, je_cursor=…, aje_cursor=…)`.
Returns the **actual journal lines** under a cell, split into two parallel samples:

```
scope:           {report, row_num, label, column, amount}
cell_value, total_sum
je_total_sum, aje_total_sum, je_total_count, aje_total_count, accounts_involved
je_lines:  [{line_id, entry_id, entry_date, entry_reference, entry_description,
             account_no, account_name, counterparty, line_description,
             debit, credit, net, cf_line_class, source:"ledger"}]
aje_lines: [ ...same shape, source:"aje" ]
je_next_cursor, aje_next_cursor          # paginate each source independently
sum_matches_cell: bool                   # the reconciliation guarantee
```
`net = debit − credit`. The JE (ledger) and AJE (Controller-Layer) samples net to
the clicked cell; **`sum_matches_cell` must be `true`**. Paginate with the cursors
(`limit` 1–200). `view` controls whether AJE lines are included (`lucid` = both).

**Only drill detail, non-zero cells.** `drilldown` returns nothing for aggregator
rows (`is_subtotal: true` — subtotals / net-sections / grand-totals — plus
headers, balance anchors, and check rows; `sum_matches_cell` comes back false) and
for `0`/`null` cells (no lines). Screen them out first — to understand a subtotal
use `explain` (it shows the children), not `drilldown`. The `lucid:explain-and-audit`
skill and `lucid_utils.py drillable` automate this screening.

---

## Sign conventions

- **P&L / BVA:** revenue and expenses are both **positive**; Operating Income /
  Net Profit are revenue − expenses, so a **loss is negative**.
- **Balance sheet:** asset balances **positive**, liability & equity balances
  **negative**. So `total_assets > 0`, `total_liabilities < 0`, `total_equity < 0`,
  and they sum to ~0. When presenting to a human, flip the sign of liabilities/
  equity so they read as positive magnitudes.
- **Trial balance:** `balance` + = debit (asset/expense), − = credit (liab/equity/rev).
- **Cash flow:** inflows positive, outflows negative; `total_change` (read `totals.total_change`, not a row number) =
  closing − opening cash.
