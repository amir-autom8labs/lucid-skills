---
name: balance-sheet-review
description: >-
  analyze-statement intent for the balance sheet: liquidity and financial position AS
  OF A DATE on the Lucid connector — working capital, current / quick ratio, cash ON
  HAND, accounts receivable and payable, intercompany balances, equity structure, and
  the assets = liabilities + equity tie-out. Use this WHENEVER the question is a
  point-in-time balance-sheet read: "what's our liquidity", "working capital",
  "current / quick ratio", "accounts receivable/payable", "how much cash do we HAVE
  right now" (the on-hand total), "what do we own / owe", "equity", "are we
  solvent", "intercompany balances". Do NOT use it for: cash FLOW /
  BURN / RUNWAY, nor the CASH POOL and anything that SPLITS or TRACKS it — cash by
  bank account, cash by currency, or the cash level month by month → cash-and-runway,
  which owns the pool; the WHOLE-business "how are we doing" snapshot →
  financial-position-review; proving one figure → explain-and-audit. This reads ONE
  statement (the balance sheet), not the whole set.
---

# Balance-sheet review — liquidity & financial position

The balance sheet answers three questions as of one date: **what do we own**
(assets), **what do we owe** (liabilities), and **what's left for owners**
(equity). Liquidity — can we pay what's due soon — falls straight out of the
current section. Your job: pull one snapshot, **prove it ties out**, then translate
Lucid's signed ledger numbers into the positive magnitudes a human reads, and
compute the liquidity ratios with the signs handled correctly.

The shared mechanics — entity resolution, period/view grammar, the money
envelope, and tie-out discipline — live in the tool docstrings and the system
prompt. This file covers only what's specific to the balance sheet.

## The mental model: a snapshot, not a flow

The balance sheet is a **point-in-time snapshot** — the position *as of* the period
end. `period` like `2025-03` means "as of 31 Mar 2025", not "during March". So:

- **Never *sum* months.** A stock doesn't accumulate: March plus April is a
  meaningless number, so `compare` / `include_trend` must never be used to *total*
  periods the way you would a P&L or a cash flow. (Those are flows; the balance
  sheet is a stock.)
- **But a *series of snapshots* is legitimate — and cheap.** "What did the position
  look like each month?" asks for twelve month-*ends*, not a sum, and it is **one
  call**: pass the months explicitly —
  `get_balance_sheet(company, period="2025-12", periods="2025-01,2025-02, … ,2025-12",
  view="lucid", density="summary")` — and every row comes back with a `series`
  aligned to your `periods` order. `include_trend=True` does the same as a
  12-element trailing array. Read each element as its own month-end position; never
  add them together.
- **Never rebuild a monthly series with one `explain` per month.** `explain`
  resolves a **single cell** for a **single period** — it is not a time-series tool.
  Twelve `explain` calls to draw a twelve-month line is the wrong tool twelve times
  over; one `periods=` call is the right tool once.
- To see the position at a single different date, just ask for that period.

### Cash position over time → hand off to the cash flow

For the **cash level month by month**, don't stack balance-sheet snapshots: the
tied-out month-end cash series is the cash-flow report's `closing_cash` row pulled
with `periods=` — the same figures, but delivered with their reconciliation
(`tieout.per_month[]`), so you can say they're proven.

And anything that **decomposes** cash — by bank account, by currency, cash pool vs
credit-card pool — belongs to **cash-and-runway**, which owns the cash pool. That
split *is* available as system data: `get_cash_composition` returns the cash-pool
accounts grouped by each account's denomination with **backend-computed
per-currency subtotals** (plus its own `tie_delta` against the cash flow). Hand off
to `cash-and-runway` for it rather than inventing a split out of balance-sheet rows,
and **never add per-account balances up yourself into a per-bank or per-currency
total** — every reported number is computed once in the backend; read the subtotal
row. The balance sheet's job here is the liquidity ratios built on the totals it can
name by `role`, plus the on-hand cash figure — which comes from the payload's
**`totals.cash`** block, never from a balance-sheet ROW. A BS cash row is an
ordinary leaf with no identity of its own, and cash need not equal any row: it
is the balance of the accounts ticked as cash, counted per account wherever the
statement presents them. The backend publishes the figure, so read `amount`
verbatim. If it carries `disclosures`, the figure and the statement's cash lines
part somewhere: an "includes …" clause means part of the cash is presented
outside a cash class (under another class, or on no Balance Sheet row), and an
"excludes …" clause means a cash class also holds accounts that are not cash,
so its line is not all cash. Print every clause beside the number. An
"includes" clause comes with a reconciliation line from
`totals.cash.components` — "of which $X presented under <class>"; an "excludes"
clause has no amount on the wire, so print it on its own
(`scripts/bs_review.py` prints the clauses and the reconciliation lines). The figure is still the cash figure; never
add that other class's row to it, because the row also holds accounts that are
not cash.

## THE SIGN CONVENTION — read this twice

This is the one thing that trips everyone up. In Lucid's ledger:

- **Asset balances are POSITIVE.**
- **Liability and equity balances are NEGATIVE.**
- The three sum to ~0: `total_assets + total_liabilities + total_equity == 0`.

So in `totals`: `total_assets > 0`, `total_liabilities < 0`, `total_equity < 0`.
That's correct double-entry, not an error. **When you present to a human, FLIP the
sign** of liabilities and equity so they read as positive magnitudes, and state the
identity as **total assets = total liabilities + equity** (all positive). Never show
a CFO "liabilities: −$3,800,000" — show "liabilities: $3,800,000 owed".

The provided script does every flip for you; if you do any math by hand, be explicit
about which numbers are signed.

## Tie-out first

Before trusting a single figure, confirm `totals.balance_check_delta == 0` (the
in-template check row carries `role: check`). Zero means assets fully reconcile against liabilities +
equity. If it's non-zero, **say so prominently** and treat the figures as suspect —
that's a books problem, not something to paper over.

## Row map (balance sheet template)

Row numbers and labels below are **illustrative** — they're configured per company
in the report template, so confirm them against `reference/report-reference.md`
for the entity you're on. Prefer the stable
`totals.*` keys (`total_assets`, `total_liabilities`, `total_equity`,
`balance_check_delta`) over hard-coded rows when you just need the headline totals.
Bind every headline to its `role` (`total_current_assets`,
`total_current_liabilities`, `total_long_term_liabilities`, `total_assets`,
`total_equity`, `pl_loss_profit`) or to the `totals` block. The row numbers in
the table below are ONE company's layout — use them only as a `row` argument to
`explain` / `drilldown` after reading them off the response you are holding, and
never as a way to find a line.

| row | line | section |
|---|---|---|
| 5 | Cash and cash equivalents | assets |
| 8 | Accounts Receivable | assets |
| 11 | Other receivable | assets |
| 12 / 13 / 14 | Intercompany (per related entity) | assets |
| **16** | **Total Current Assets** | assets |
| 21 | Intercompany (long-term) | assets |
| **24** | **TOTAL ASSETS** | assets |
| 29 | Accounts Payable | liabilities |
| 32 | Deferred Income | liabilities |
| **35** | **Total Current Liabilities** | liabilities |
| 39 | SAFE | liabilities |
| 40–43 | Intercompany (long-term) | liabilities |
| **44** | **Total Long-Term Liabilities** | liabilities |
| 46 / 51 | Share capital / Add'l Paid-in Capital | equity |
| 55 / 56 | Current-year P&L / Retained earnings | equity |
| **57** | **Total Equity** | equity |
| **59** | **TOTAL LIABILITIES & EQUITY** | equity |
| 60 | check (should be 0) | check |
| 66–84 | Notes 1–2 (Other receivable / Other current liabilities detail) | note |

## Derived liquidity metrics — be careful with signs

Remember current liabilities (`role: total_current_liabilities`) arrive
**negative**. Work it through:

- **Working capital = Total Current Assets + Total Current Liabilities**
  = `role:total_current_assets + role:total_current_liabilities`. Because current
  liabilities are negative on the wire, a plain **addition already nets
  correctly** (assets minus the magnitude of what's due soon). Do **not** subtract —
  that would cancel the sign and double-count. Positive working capital = a cushion;
  negative = current obligations exceed current assets (a liquidity warning).

- **Current ratio = Total Current Assets ÷ |Total Current Liabilities|**
  = `role:total_current_assets / abs(role:total_current_liabilities)`. Take the
  **absolute value** of the (negative) liability. >1 means current assets cover
  current liabilities; ~2x is comfortable; <1 is a flag.

- **Quick ratio (acid test) = (Cash + AR) ÷ |Total Current Liabilities|** —
  **not computed, and you must not compute it either.** It needs the cash and
  accounts-receivable LEAVES, and neither can be named on the wire: a BS detail
  row's label is the company's own `main_class`, so nothing identifies which of
  their mains means "accounts receivable". The script reports it as *not
  computed* with the reason. Reaching for a row number here — or matching a
  label like "Accounts receivable", which simply fails on a company that writes
  "Trade debtors" — produces an acid test on the wrong lines, and this is a
  ratio a reader acts on.

The script computes what it can with the signs handled, and explicitly declines
the rest. If you compute by hand, write the `abs()` explicitly so a reviewer can
see you didn't drop a sign — and decline anything you cannot name by identity.

## Intercompany balances

For a group, intercompany balances are receivables/payables *between* entities.
Within a single entity they're real positions; **across a consolidated group they
should net to ~0** (one entity's receivable is another's payable).

**Do NOT compute that net, and do not name the rows by number.** The script
reports `Net intercompany  not computed` and says why, and you must not fill the
gap yourself. Intercompany rows are account-level BS leaves: they carry no
`role`, no `heading_key`, no identity of any kind, and their labels are the
tenant's own `main_class` text. The row numbers that used to appear here
(12/13/14, 21, 40–43) are one reference chart's coordinates — on another chart they are
whichever assets and liabilities that tenant's routing ordered into those slots,
and netting them produces a group exposure figure computed from unrelated lines.

Consolidation is the one place a reader has no independent sense of what the
number should be, so a wrong one is undetectable by the person most likely to
catch it anywhere else. Say the net could not be identified, and point at
Reports → Balance Sheet on the consolidated view where the lines are labelled.

## Equity structure (and the sign trap)

Equity = share capital + paid-in capital + accumulated retained earnings/losses +
current-year P&L. **Mind the wire sign:** healthy *positive* book equity is stored
**negative** (a credit balance), so a negative `total_equity` is normal and good.
Real **negative book equity** (a deficit) shows up as a *positive* `total_equity`
on the wire (a debit balance) — that's the alarm condition, when accumulated losses
exceed paid-in capital. Test it by sign-flipping: `displayed_equity = -total_equity`;
if that is **< 0**, equity is in deficit. The fastest cross-check is the tie-out
identity — `assets = |liabilities| + displayed_equity` — which only holds when the
signs are read correctly.

A common growth-company shape is **positive but eroding equity**: large paid-in
capital, a deep accumulated-loss line, and a still-positive total. That's a watch
item (equity is shrinking each loss-making period), not yet a deficit — say which
one it is.

What the script actually surfaces: the sign-flipped **total equity**
(`role: total_equity`) and a true deficit flag (`displayed_equity < 0`), plus the
**current-year P&L** line (`role: pl_loss_profit`). It reports *share capital +
APIC* and the *accumulated earnings/(losses)* line as **not identified**, and you
must not reconstruct either. Both are account-level leaves with no identity on
the wire; retained earnings in particular has none, so `retained + current-year`
computed from only the half that resolves is short by the entire opening
position while still looking like a total. A partial sum presented as
"accumulated earnings" is a wrong number, not a partial one.

## Workflow

1. **Resolve the company** (`search_entities` → exact `code`).
2. **Pull one snapshot:** `get_balance_sheet(company, period="YYYY-MM",
   view="lucid", density="summary")`. `density=summary` returns the statement
   face — cash, AR, the current subtotals, the totals — each with its `row_num`,
   without the note appendix; that's everything the liquidity math needs, read
   inline. Default to `lucid` (close-ready); say which view you used. For a single
   date, skip `compare` / `include_trend`. If the question is the position **across
   months**, add `periods="2025-01, … ,2025-12"` (or `include_trend=True`) to *this
   same call* and read each row's aligned `series` as a run of month-end snapshots —
   one call, twelve dates, never a sum. Either way that's call #1 — and usually the
   only call you need.
3. **(Optional) account detail:** if a line needs breaking down (e.g. *what's in*
   AR or other current liabilities), one `get_trial_balance(company, period,
   view="lucid")` call, or `explain`/`drilldown` on the specific BS row. Stay at
   **≤2 single-period calls.**
4. **If a result spills to a file** (e.g. a full trial-balance pull), don't read
   the raw JSON — run the script or the `lucid_utils` CLI (relative paths from the
   skill dir) on the path:
   ```bash
   python scripts/bs_review.py <bs.json>
   python scripts/lucid_utils.py totals <bs.json>
   ```
5. **Check the tie-out, then present** in the output structure below.

## Answering

Follow the answer contract in `lucid-platform-guide`, applied to a balance-sheet read.

Lead with the tie-out, then the position in this order: what the company owns
(asset mix, any concentration — e.g. nearly all cash); what it owes (AP, current
liabilities, SAFE / long-term); what's left for owners (equity — positive,
eroding, or a true deficit, read with the sign trap in mind); and how liquid it is
(a working-capital cushion or squeeze; current/quick ratios comfortable or a flag).

- **Quote the headline figures** (cash, total current assets, total assets, total
  current liabilities, total liabilities, total equity) from `totals` / the role
  rows, presented as the positive magnitudes a human reads — liabilities and
  equity arrive **negative**, so flip the sign for display and say "owed" or
  "positive equity", never print `−4,400,000` as equity.
- **Working capital and the current / quick ratios are derived.** Compute them
  with `scripts/bs_review.py` (or `lucid_utils`) from the reported components,
  never mentally, and say what each is built from. A ratio needing a line the
  script reports as *not identified* (e.g. AR on some charts) is not computed —
  say so rather than approximating.
- Use a compact table for the position scorecard.
- Close with 2–3 follow-ups such as "Break down what's in AR?" or "Net the
  intercompany balances across the group?".

Call positive book equity positive, and flag a genuine deficit
(`displayed_equity < 0`) as the alarm. Always name the view and period.

## Illustrative example — fictional company (Acme Inc.), synthetic figures

Line names below are labels, not addresses. Each headline resolves by its
`role`; the leaves (cash, receivables, payables) resolve by nothing, which is
why this skill reports them as *not identified* rather than reading a row.

`get_balance_sheet(company="ACME", period="2025-03", view="lucid")`:

| line | wire value | presented |
|---|---:|---:|
| Cash | 8,000,000 | $8,000,000 |
| Accounts receivable | 120,000 | $120,000 |
| Total current assets | 8,100,000 | $8,100,000 |
| **TOTAL ASSETS** | 8,200,000 | **$8,200,000** |
| Accounts payable | −200,000 | $200,000 owed |
| Total current liabilities | −700,000 | $700,000 |
| SAFE | −3,000,000 | $3,000,000 |
| **Total liabilities** | −3,800,000 | **$3,800,000** |
| **Total equity** | −4,400,000 | **$4,400,000 (positive equity)** |
| `balance_check_delta` | 0 | **ties out ✅** |

**Liquidity:**
- Working capital = 8,100,000 + (−700,000) = **$7,400,000** (large cushion).
- Current ratio = 8,100,000 ÷ |−700,000| ≈ **11.57x** — very liquid.
- Quick ratio = (8,000,000 + 120,000) ÷ 700,000 ≈ **11.60x**.

**Tie-out:** 8,200,000 + (−3,800,000) + (−4,400,000) = **0** ✅.

**Flag — equity:** total equity is **positive, +$4.4M** (sign-flipped from the
−$4,400,000 wire value): assets $8.2M = liabilities $3.8M + equity $4.4M. But
it's **eroding** — ~$15M of paid-in capital against ~$10.6M of accumulated losses
(retained-earnings deficit + the current-year loss), with a $3M SAFE parked in
long-term liabilities. **Call this out:** strong near-term liquidity (11.6x current
ratio, ~$8M cash) and still-positive book equity, but each loss-making quarter
draws that cushion down. It is *not* a deficit today — don't call it one — but the
trajectory is the thing to watch. Liquidity ≠ long-run solvency; say both.

## Constraints

- **Read-only.** Never imply you can post or change anything.
- **≤2 Lucid calls.** A multi-month position is **one** of them (`periods=` or
  `include_trend=True`), never twelve single-period pulls and never an `explain` per
  month. Don't add `include_composition` to a validation pull, and never sum
  snapshots — the balance sheet is a stock.
- **Cash decomposition isn't yours.** Monthly cash levels and any split of cash by
  bank or currency → `cash-and-runway` (`get_cash_composition` for the split); never
  total per-account balances yourself.
- Default `view="lucid"`; state the view used.
- **Projected accruals.** In `lucid` with projections included, an open month's
  balance sheet carries one Lucid-owned current-liability line, *Projected
  accruals*: the other side of the projected P&L entries (recurring costs not
  booked yet), whose P&L side lowers the current-year result in equity. It is an
  estimate, not a creditor.
  When it is non-zero, name it and its amount, and leave it out of any judgement
  about real obligations (it is zero with `include_projections=false`).
- Always run the tie-out check and report it.
- On spilled files, use the script / `lucid_utils` CLI — don't reload raw JSON.
- The Acme Mar-2025 figures above are an illustrative, synthetic example — use them
  to understand the mechanics, not as real data for any company.
