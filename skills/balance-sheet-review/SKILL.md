---
name: balance-sheet-review
description: >-
  Review liquidity and financial position from the balance sheet using the Lucid
  CFO connector — working capital, current/quick ratio, cash, accounts receivable
  and payable, intercompany balances, equity structure, and the asset = liability +
  equity tie-out. Use this WHENEVER the question is about the balance sheet or
  financial position as of a date: "what's our liquidity", "working capital",
  "current ratio", "quick ratio", "accounts receivable/payable", "how much cash do
  we have", "what do we own / what do we owe", "equity", "net assets", "book value",
  "are we solvent", "intercompany balances", or "financial position". Pulls
  get_balance_sheet (a point-in-time snapshot) and optionally get_trial_balance for
  account-level detail. Read lucid:lucid-platform-guide first for the shared
  mechanics this builds on.
---

# Balance-sheet review — liquidity & financial position

The balance sheet answers three questions as of one date: **what do we own**
(assets), **what do we owe** (liabilities), and **what's left for owners**
(equity). Liquidity — can we pay what's due soon — falls straight out of the
current section. Your job: pull one snapshot, **prove it ties out**, then translate
Lucid's signed ledger numbers into the positive magnitudes a human reads, and
compute the liquidity ratios with the signs handled correctly.

This skill builds on `lucid:lucid-platform-guide` — read it first for entity
resolution, period/view grammar, the money envelope, and tie-out discipline. This
file covers only what's specific to the balance sheet.

## The mental model: a snapshot, not a flow

The balance sheet is a **point-in-time snapshot** — the position *as of* the period
end. `period` like `2025-03` means "as of 31 Mar 2025", not "during March". So:

- **Never** use `compare` / `include_trend` to "add up" months — a balance sheet
  doesn't accumulate. One period = one snapshot. (P&L and cash flow are flows; the
  balance sheet is a stock.)
- To see the position at a different date, just ask for that period.

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

Before trusting a single figure, confirm `totals.balance_check_delta == 0` (row 60
is the in-template check). Zero means assets fully reconcile against liabilities +
equity. If it's non-zero, **say so prominently** and treat the figures as suspect —
that's a books problem, not something to paper over.

## Row map (balance sheet template)

Row numbers and labels below are **illustrative** — they're configured per company
in the report template, so confirm them against the platform guide's
`reference/report-reference.md` for the entity you're on. Prefer the stable
`totals.*` keys (`total_assets`, `total_liabilities`, `total_equity`,
`balance_check_delta`) over hard-coded rows when you just need the headline totals.
Use the row numbers with `find_row` and for `explain`/`drilldown`.

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

Remember current liabilities (row 35) arrive **negative**. Work it through:

- **Working capital = Total Current Assets + Total Current Liabilities**
  = `row16 + row35`. Because row 35 is negative, a plain **addition already nets
  correctly** (assets minus the magnitude of what's due soon). Do **not** subtract —
  that would cancel the sign and double-count. Positive working capital = a cushion;
  negative = current obligations exceed current assets (a liquidity warning).

- **Current ratio = Total Current Assets ÷ |Total Current Liabilities|**
  = `row16 / abs(row35)`. Take the **absolute value** of the (negative) liability.
  >1 means current assets cover current liabilities; ~2x is comfortable; <1 is a
  flag.

- **Quick ratio (acid test) = (Cash + AR) ÷ |Total Current Liabilities|**
  = `(row5 + row8) / abs(row35)`. Excludes slower-moving current assets; the
  sterner liquidity test.

The script computes all three with the signs handled. If you compute by hand, write
the `abs()` explicitly so a reviewer can see you didn't drop a sign.

## Intercompany balances

For a group, intercompany rows (12/13/14, 21, 40–43) are receivables/payables
*between* entities. Within a single entity they're real positions; **across a
consolidated group they should net to ~0** (one entity's receivable is another's
payable). Surface the net — a large non-zero net intercompany balance on a
consolidation is worth flagging (elimination not done, or a genuine cross-entity
exposure). The script reports the net; use `explain`/`drilldown` on a row to see the
counterparty if it looks off.

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
capital, a deep accumulated-loss line (rows 55 + 56), and a still-positive total.
That's a watch item (equity is shrinking each loss-making period), not yet a
deficit — say which one it is. The script surfaces share capital + APIC, the
accumulated earnings/(losses) line, the sign-flipped total, and flags a true
deficit (`displayed_equity < 0`) distinctly from accumulated losses.

## Workflow

1. **Resolve the company** (`search_entities` → exact `code`). See platform guide.
2. **Pull one snapshot:** `get_balance_sheet(company, period="YYYY-MM", view="lucid")`.
   Default to `lucid` (close-ready); say which view you used. **No `compare` /
   `include_trend`.** That's call #1 — and usually the only call you need.
3. **(Optional) account detail:** if a line needs breaking down (e.g. *what's in*
   AR or other current liabilities), one `get_trial_balance(company, period,
   view="lucid")` call, or `explain`/`drilldown` on the specific BS row. Stay at
   **≤2 single-period calls.**
4. **If a result spills to a file**, don't read the raw JSON — run the script or the
   `lucid_utils` CLI on the path:
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/skills/balance-sheet-review/scripts/bs_review.py <bs.json>
   python ${CLAUDE_PLUGIN_ROOT}/skills/balance-sheet-review/scripts/lucid_utils.py totals <bs.json>
   ```
5. **Check the tie-out, then present** in the output structure below.

## Output structure

Report in this order:

1. **Assets** — cash, AR, total current assets, total assets (positive magnitudes).
2. **Liabilities** — AP, current liabilities, SAFE / long-term, total liabilities
   (sign-flipped to positive). State **assets = liabilities + equity**.
3. **Equity** — share capital + APIC, accumulated earnings/(losses), total book
   equity (sign-flipped). Flag negative book equity.
4. **Liquidity** — working capital, current ratio, quick ratio (with the sign math
   shown or trusted from the script).
5. **Notable items / flags** — negative equity, thin/negative working capital, large
   net intercompany, concentration in one asset (e.g. nearly all cash), deferred
   income, sizable SAFE.
6. **Tie-out** — `balance_check_delta` and whether it's 0.

## Illustrative example — fictional company (Acme Inc.), synthetic figures

`get_balance_sheet(company="ACME", period="2025-03", view="lucid")`:

| line | wire value | presented |
|---|---:|---:|
| Cash (row 5) | 8,000,000 | $8,000,000 |
| Accounts receivable (row 8) | 120,000 | $120,000 |
| Total current assets (row 16) | 8,100,000 | $8,100,000 |
| **TOTAL ASSETS (row 24)** | 8,200,000 | **$8,200,000** |
| Accounts payable (row 29) | −200,000 | $200,000 owed |
| Total current liabilities (row 35) | −700,000 | $700,000 |
| SAFE (row 39) | −3,000,000 | $3,000,000 |
| **Total liabilities** | −3,800,000 | **$3,800,000** |
| **Total equity (row 57)** | −4,400,000 | **$4,400,000 (positive equity)** |
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
- **≤2 single-period Lucid calls.** No `compare` / `include_trend` /
  `include_composition` — the balance sheet is a snapshot.
- Default `view="lucid"`; state the view used.
- Always run the tie-out check and report it.
- On spilled files, use the script / `lucid_utils` CLI — don't reload raw JSON.
- The Acme Mar-2025 figures above are an illustrative, synthetic example — use them
  to understand the mechanics, not as real data for any company.
