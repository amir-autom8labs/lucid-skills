# Lucid report reference — row maps & response shapes

The exact JSON shape of every tool response, plus the **typical** report layout.
Row numbers are stable across periods, so they're how you read subtotals and how
you target `explain` / `drilldown`. All money fields are the envelope
`{"amount": "1234.56", "currency": "USD", "units": "major"}` unless noted.

> **Row numbers and line labels are configured per company.** The report templates
> are mapped to each company's chart of accounts, so the exact `row_num`, `label`,
> which lines exist, and the note/detail ranges **vary between companies**. Treat
> the maps below as the *typical* layout and a starting point — always read the
> actual `row_num` / `label` / `section` from the response before relying on them
> (especially for `explain` / `drilldown`). What **is** stable across companies is
> the **schema**: the response field names, the `totals` keys (e.g.
> `totals.net_profit`, `totals.total_assets`), the `tieout` block, the section
> vocabulary, and the sign conventions. Prefer the `totals` keys for headline
> figures; use row numbers for line-level detail.

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

## Dashboard
`get_dashboard(company, period, view)`. KPIs **mix units** — read each by its `unit`.

```
kpis: [ {kind, label, amount, unit, delta, delta_unit, comparator, sparkline, sparkline_unit} ]
opex_donut: { slices: [{label, amount}], total }
tie_out_ok: bool
```
- `kind` ∈ `cash | runway | revenue_qtd | gross_margin` (always in that order).
- `unit`: `cents` → `amount` is a money envelope; `months` → `amount` is an int
  (runway; `null` = unbounded / profitable); `bps` → `amount` is an int basis-
  points×100 (`-3966` = **−39.66%**, divide by 100 for percent).
- `delta_unit`: `currency` (money envelope) | `pct` (int bps×100, relative) |
  `pp` (int bps×100, percentage-points) | `null`.
- `comparator` is human copy ("vs Feb 2025", "YoY (vs Q1 2024)", "at current burn").
- Donut slices are R&D / S&M / G&A; `total` = Σ slices = total OpEx.

---

## P&L
`get_pl(...)`. `rows[]`: `{row_num, label, section, is_subtotal, amount, series, trend, fy_ytd}`.
`section` ∈ `summary` (row_num ≤ 30) | `note` (row_num ≥ 33, expandable detail).

**Headline rows (section `summary`):**
| row | line |
|---|---|
| 5 | Revenues |
| 6 | COGS |
| **7** | **Gross Margin** (subtotal) |
| 8 | % Gross Margin |
| 10 / 11 / 12 | R&D / S&M / G&A |
| **13** | **Total operating expenses** (subtotal) |
| **15** | **Operating income / (Loss)** (subtotal) |
| 17 / 18 | Financial / Other expenses (income) |
| **19** | **Income (Loss) before tax** (subtotal) |
| 21 | Taxes on income |
| 22 | Equity in Earnings of Subsidiary |
| **24** | **Net Profit / (Loss)** (subtotal) |
| 25 | Adjusted Net Profit |
| 27 | Total expenses |
| 29 | Depreciation |
| **30** | **EBITDA** (subtotal) |

Notes (detail, row_num ≥ 33): Note 1 Revenues (35–53), Note 2 COGS (58–84),
Note 3 R&D (86–106), Note 4 S&M (109–137), Note 5 G&A (140–175), Note 6 Financial
(178–191), Note 7 Other (194–198), Note 8 Taxes (201–208).

**`totals`:** `{revenues, gross_margin, operating_income, ebitda, net_profit, check_delta, series_check_delta}`.
Tied out when `check_delta == 0`.

---

## Balance sheet
`get_balance_sheet(...)`. `rows[]`: `{row_num, label, section, is_subtotal, amount, series, trend, fy_ytd}`.
`section` ∈ `assets | liabilities | equity | note | check`.

| row | line |
|---|---|
| 5 | Cash and Cash equivalents |
| 6 | Restricted Cash and Deposits |
| 7 | Short term deposits |
| 8 | Accounts Receivable |
| 11 | Other receivable |
| 12–14 | Intercompany (one row per related entity) |
| **16** | **Total Current Assets** |
| 19 / 20 | Fixed assets / Accumulated depreciation |
| 22 | Lease right-of-use assets |
| **24** | **TOTAL ASSETS** |
| 27 | Credit cards B.S |
| 29 | Accounts Payable |
| 32 | Deferred Income |
| 33 | Other current liabilities |
| **35** | **Total Current Liabilities** |
| 39 | SAFE |
| **44** | **Total Long-Term Liabilities** |
| 46 | Share capital |
| 51 | Add'l Paid-in Capital |
| 55 | Current-year P&L Loss (Profit) |
| 56 | Retained earnings |
| **57** | **Total Equity** |
| **59** | **TOTAL LIABILITIES & EQUITY** |
| 60 | check (should be 0) |
| 66–84 | Notes 1–2 (Other receivable / Other current liabilities detail) |

**`totals`:** `{total_assets, total_liabilities, total_equity, balance_check_delta, series_check_delta}`.
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
`9999` "Other / unclassified" may appear — non-zero there means lines fell
outside the classification map.

**`totals`:** `{net_operating, net_investing, net_financing, total_change, opening_cash_start, closing_cash_end, series_check_delta}`.
**`tieout`:** `{per_month: [{month, classified, bank_delta, delta}], classified_total, bank_delta_total, period_delta}`.
Tied out when `period_delta == 0` (classified cash flow == actual bank-balance change).

---

## BVA
`get_bva(...)`. Same row skeleton as P&L (`section` ∈ `summary | note`), but each
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

---

## Sign conventions

- **P&L / BVA:** revenue and expenses are both **positive**; Operating Income /
  Net Profit are revenue − expenses, so a **loss is negative**.
- **Balance sheet:** asset balances **positive**, liability & equity balances
  **negative**. So `total_assets > 0`, `total_liabilities < 0`, `total_equity < 0`,
  and they sum to ~0. When presenting to a human, flip the sign of liabilities/
  equity so they read as positive magnitudes.
- **Trial balance:** `balance` + = debit (asset/expense), − = credit (liab/equity/rev).
- **Cash flow:** inflows positive, outflows negative; `total_change` (row 41) =
  closing − opening cash.
