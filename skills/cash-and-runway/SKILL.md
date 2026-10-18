---
name: cash-and-runway
description: >-
  analyze-statement intent for cash: cash BURN, RUNWAY, cash-FLOW analysis, and THE CASH
  POOL ITSELF on the Lucid connector. Use this WHENEVER someone asks "what's our runway",
  "what's our burn rate", "how many months of cash left", "what's draining cash", "where
  did the cash go", any cash-FLOW / trajectory question — and ALSO whenever the cash
  balance must be TRACKED OVER TIME or BROKEN DOWN: "cash per month", "cash by bank
  account", "cash by currency", "which banks hold the cash". It owns the cash pool: it
  pulls the direct-method cash flow, verifies the tie-out (classified flow ==
  bank-balance delta), reads month-end levels off the closing-cash series, and separates
  durable operating burn from one-off financing / investing swings that flatter total
  cash. Do NOT use it for the SINGLE point-in-time cash balance with liquidity / working
  capital → balance-sheet-review; nor P&L profitability / margins →
  pl-and-margin-analysis; nor the whole-business "how are we doing" snapshot →
  financial-position-review.
---

# Cash & runway

Answer the four questions a founder loses sleep over: **How much cash do we
have? How fast are we spending it? How long does it last? What's eating it?**
The connector mechanics (entity resolution, period grammar, view modes, the
money envelope) come from the tool docstrings and the system prompt. Here we
focus on the cash-specific reasoning that's easy to get wrong.

## Why this is subtle

The headline cash balance moves for two very different reasons, and conflating
them produces dangerously wrong runway numbers:

- **Operating burn** — cash consumed running the business (payroll, R&D, rent,
  collections). This is the **durable** signal. It's roughly the same every month
  and it's what runway should be built on.
- **One-off financing / investing swings** — a SAFE raise, an equity round, an
  intercompany sweep, a deposit moving. These can dwarf a month's operating burn
  and make total cash *rise* in a month the company is bleeding operationally.

A company can raise a $3M SAFE and show cash *up* for the month while burning
~$450K/month operationally. Runway off "total cash change" would look infinite;
runway off operating burn is the truth. **Always separate the two and state
which you used.**

## The sources

| Need | Tool | Key fields |
|---|---|---|
| Burn composition + drivers + tie-out | `get_cash_flow_direct` | `totals`, `rows`, `tieout` |
| Cash level **month by month** | `get_cash_flow_direct(periods=…)` | `closing_cash` row `series`, `tieout.per_month[]` |
| Cash **split by currency / by bank** | `get_cash_composition` | `currency_subtotal` rows, `totals.tie_delta`, `totals.basis` |
| Which accounts *are* the cash pool (metadata, no figures) | `list_accounts(cash_pool_only=true)` | `account_no`, `account_desc`, `currency`, pool flags |
| Cash position on the books at period end | `get_cash_composition` | `totals` (the backend-resolved cash pool — the balance sheet's own cash LEAF has no identity on the wire, so it cannot be read by row) |

| Precomputed **runway**, **cash** and **burn** KPIs | `get_status(sections=["kpis"])` | the `runway` / `cash` / `burn` cards |

> **Runway is back, and it is one call.** `get_status(company, sections=["kpis"])`
> serves the same backend-computed KPI strip the CFO dashboard draws
> — including `runway`, whose `amount` is a count of **months**
> and NOT money. Quote it verbatim; single-source-of-truth still forbids doing
> the `cash ÷ burn` division yourself. Read the three nulls exactly:
> `runway.amount: null` means **the company is not burning (or cash could not be
> identified)** — its `comparator` says which, and it is never "no months left";
> `provisional: true` means the month is not closed and the figure can still
> move; `delta: null` means no comparison exists, not a flat month.

**Cash is never projected.** Lucid's projected entries (estimates of recurring
P&L entries not booked yet in an open month) never reach the direct cash flow,
the cash composition or the cash pool: every cash figure here is booked. Do not
confuse them with the dashboard's `cash.projection` (a straight-line runway
extrapolation, labelled `projected`). Burn and runway are booked too; a margin
or other P&L figure quoted next to cash can include projections — say so when
it does.

Default `view="lucid"` and `density="summary"`, default to a single recent month,
and resolve the company with `search_entities` first (never guess a handle). Keep
it to **≤2 calls** — and when the question spans months, that means **one**
`periods=` call covering all of them (see "Cash position, monthly" below), never one
call per month. "Cash by bank and by currency, monthly" is the full two: the level
(`get_cash_flow_direct`) and the split (`get_cash_composition`).

## Direct cash-flow structure

`get_cash_flow_direct` is the spine. The numbers you cite live in named rows
**and** in the `totals` block (use either; they agree). Row numbers and labels
below are **illustrative** — they're configured per company in the report mapping
(see `reference/report-reference.md`); prefer the
stable `totals.*` keys (`net_operating`, `total_change`, `opening_cash_start`,
`closing_cash_end`) for headline figures:

| Row | `row_type` | Line | `totals` key |
|---|---|---|---|
| 6 | `detail_cf_class` | Collection from customers (the inflow) | — |
| 8–18 | `ref` / `detail_*` | Operating cash out (COGS/R&D/S&M/G&A ref rows 8–13, payroll 16, VAT, tax) | — |
| 19 | `subtotal` | Total expenses paid in cash | — |
| **21** | `net_section` | **Net cash — operating** (the burn line) | `net_operating` |
| 24–30 | `detail_cf_class` | Investing detail | — |
| **31** | `net_section` | **Net cash — investing** | `net_investing` |
| 34–38 | `detail_cf_class` | Financing detail (loans, options, **SAFE row 36**, equity) | — |
| **39** | `net_section` | **Net cash — financing** | `net_financing` |
| **41** | `grand_total` | **Total increase/(decrease) in cash** | `total_change` |
| 43 | `opening_cash` | Cash at beginning of period | `opening_cash_start` |
| 44 | `closing_cash` | Cash at end of period | `closing_cash_end` |
| 45 | `check` | Should be 0 | — |
| 62+ | `breakdown` | Per-category note detail, linked by `parent`/`group_key` | — |

`section` ∈ `operating | investing | financing | meta | breakdown | other`.
The `ref` rows (8–13) are headline category totals; their per-line detail
(e.g. which R&D line) sits in the `breakdown` section, joined by `parent` =
the row's `group_key`. **Sign convention: inflows positive, outflows negative**;
`total_change` (41) = closing − opening cash.

## MANDATORY tie-out — do this before you say a number

The direct cash flow must reconcile to the actual bank-balance change. The
check lives in `tieout`:

```
tieout.period_delta            # must be 0  (classified flow == bank delta)
tieout.per_month[].delta       # each must be 0
```

`period_delta = classified_total − bank_delta_total`. **If `period_delta` is not
0, say so prominently and treat every cash figure as suspect** — that's a books
problem (lines that didn't classify, an unreconciled bank feed), not a rounding
quirk to paper over. Also glance at row 45 (`check`) and the `unclassified` row
("Other / unclassified") — non-zero there means lines fell outside the
classification map. A controller signs off the reconciliation before presenting;
so do you.

## Cash position, monthly — one call, twelve month-ends

"How much cash did we have each month?" is a **level** question, and the levels are
already computed and reconciled for you. Do **not** rebuild them: not from twelve
single-month pulls, not from twelve `explain` calls (`explain` resolves a single
cell for a single period — it is not a time-series tool), and not by accumulating
`opening_cash_start` plus each month's `total_change` yourself. Every reported
number is computed once, in the backend; you quote it.

**Tie-out first** (as everywhere in this skill): before quoting any month, check
`tieout.per_month[].delta` — each must be 0. A month whose delta is non-zero is a
month whose cash figure you must flag as suspect, not smooth over.

Ask for the months explicitly and read the aligned per-row `series`:

```text
get_cash_flow_direct(company="ACME", period="2025-12",
                     periods="2025-01,2025-02, … ,2025-12", view="lucid",
                     density="summary")
```

- The row with `row_type == "closing_cash"` (row 44 in the illustrative map above)
  carries a `series` aligned to your `periods` order — **twelve backend-computed,
  tied-out month-end cash levels**. `opening_cash` (row 43) is the same at period
  starts. `tieout.per_month[]` gives each month's `classified` / `bank_delta` /
  `delta` alongside them.
- `density="summary"` returns both cash-level rows along with the
  operating / investing / financing net-section rows and the `totals` / `tieout`
  blocks — one small payload, **one** call. Reach for `density="detail"` only when
  you need a line's composition (the `ref` category rows and the per-category
  `breakdown` notes), and trim it with `fields` when you do.
- Quote the `series` values as they come. Don't diff or re-sum them into a "change"
  you could have read off row 41.

## Splitting cash by currency or by bank — `get_cash_composition`

The section above gives the **level**. `get_cash_composition` gives the **split**:
the cash-pool accounts grouped by the currency each account is *denominated* in,
each block closed by a backend-computed `currency_subtotal` row, then
`total_cash_pool`; the credit-card pool follows in the same shape
(`total_cc_pool`), then `closing_cash` and a `check` row.

The cash-flow report can never provide this split — its rows are keyed by cash-flow
class, and every bank↔bank transfer inside the pool is excluded by construction
(that exclusion is what makes the tie-out hold). So "how much cash do we hold, by
bank and by currency, month by month?" is **two calls**, not twelve:

```text
get_cash_flow_direct(company="ACME", period="2025-12",
                     periods="2025-01, … ,2025-12", view="lucid",
                     density="summary")     # the LEVEL: closing_cash series + tieout

get_cash_composition(company="ACME", period="2025-12",
                     periods="2025-01, … ,2025-12", view="lucid",
                     density="summary")     # the SPLIT: per-currency subtotals
```

- `density="summary"` (the **default**) returns **only** the subtotal rows — the
  per-currency subtotals, both pool totals, `closing_cash` and `check`. That is
  already the complete answer to "cash by currency, monthly", and it's a small
  payload.
- `density="detail"` adds the per-account rows — reach for it when the user wants
  the **per-bank** breakdown. `density="totals"` gives the header + `totals`
  tie-out block alone. Figures are identical across densities; only the row count
  changes.
- With `periods=`, every row carries a `series` of month-end positions aligned to
  your period order — **one** call covers the year; never loop a single-period call
  per month. A month with no backing data is `null`, not `0`.
- Cash is a **stock**: each figure is the position *at the period's end date*, not a
  movement over it. Read a `series` as a run of month-ends; never add them up.
- Match rows on `role` (`currency_subtotal`, `total_cash_pool`, `total_cc_pool`,
  `closing_cash`, `check`) and `pool` (`"cash"` | `"cc"`) — never on a positional
  index. Unlike the statement reports, these rows carry **no `row_num`**: `role` +
  `account_currency` is the identity, and `label` is tenant-authored display text.

### The rules that make this answer trustworthy

- **Quote the subtotals verbatim — never sum the leaves.** Every
  `currency_subtotal` / `total_cash_pool` / `total_cc_pool` / `closing_cash` figure
  is computed once, in the backend. Read the subtotal row. A per-currency or
  per-bank total you added up yourself is **not a reported number**.
- **Lead with the tie-out.** `totals.tie_delta` = `closing_cash − cf_closing_cash`
  (the cash flow's own closing cash) and **must be `0`**. If it isn't, the
  composition and the cash flow disagree — **say so prominently and treat every
  figure on the report as suspect.** That's a books problem, not a rounding quirk
  to smooth over.
- **Always state that these are converted amounts, not native ones.**
  `totals.basis` is `"reporting"`, which on this report means *converted*: every
  figure is a presented value, merely **grouped by** the currency each account is
  denominated in. These are **not native-currency amounts** — an ILS-denominated
  account's balance is its presented value, never "₪X". Say this whenever you
  present a currency split, because it's the misreading that turns a correct
  number into a wrong currency symbol.
- **Three currency-ish fields live on this one report, and only one of them moves
  with your `currency` argument.** Keeping them apart is the whole game:
  - the top-level **`currency`** caption — the ISO code the figures are actually
    in. Quote this one. It follows `currency=`: the entity's reporting currency by
    default, its functional currency under `currency="functional"`.
  - **`currency_mode`** — which of the two ledger bases the backend summed on
    (`"reporting"` | `"functional"`). Same axis as the caption.
  - **`totals.basis`** — pinned to `"reporting"` in *both* modes, because it
    answers a different question ("converted or native?"), not "which ledger?".
    Reading it as "these are reporting-currency amounts" would mislabel every
    figure of a functional read.
  - a row's **`account_currency`** — that account's *denomination*, the grouping
    axis. Never the unit of the number.
- **Ask for the basis the user meant.** `get_cash_composition` takes
  `currency="reporting"` (default) or `currency="functional"`. A CFO asking what
  an ILS subsidiary holds in its own books wants `"functional"` — answering on the
  reporting basis is a correct answer to a question they didn't ask. If you then
  drill or explain a figure, pass the *same* value, or the detail won't foot to it.
- **`totals.pool_configured: false` does not mean "$0 cash".** It means no account
  was ever flagged as a bank / credit-card account for this entity, so `rows` is
  empty. Say "the cash pool isn't set up for this entity — flag the bank accounts
  in **Settings → Accounts**", never report zero cash.
- **Accounts carrying no currency on the chart** get their own `"Unspecified"`
  block. Report it as such — never drop it, never fold it into another currency.
- **Bank nationality (Israeli vs foreign) is not an attribute anywhere in the
  system**, and by standing product decision we are not adding one. If asked for
  "Israeli banks vs foreign banks", say so plainly and offer the per-bank rows
  (`density="detail"`) so the user can judge from the account names themselves.

### Which accounts *are* the cash pool

`list_accounts(company, cash_pool_only=true)` names them — account number,
description, denomination, and the `is_cash_pool` / `is_cc_pool` flags
`get_cash_composition` groups by. It returns **metadata, not figures**: it carries
no balances, and you must never count, sum, or infer an amount from it. Reach for it
only for account *identity* behind the figures.

Use `cash_pool_only=true` rather than filtering or paging the whole chart: a flagged
pool account with no journal activity sorts to the very end of the listing, so a
caller reading one page deep would silently miss it.

## Burn rate — operating, over a trailing window

Burn is how fast cash is consumed: **burn = −net_operating** (a −$450,000
operating month is +$450,000 of burn). One month is noisy (timing of payroll
runs, large vendor payments), so compute an **average over a trailing window**
(3–6 months). To get several months of operating cash flow, either:

- pull a wider period (`FY2025`, `2025-Q1`) — cash flow is a **flow**, so a
  quarter sums its months for you; or
- pull a few single months and feed their `net_operating` into the script.

Don't sum single-month balance-sheet cash yourself — use the flow report.

## Runway — one call, quoted verbatim

"What's our runway?" is answered by **`get_status(company, sections=["kpis"])`**
and its `runway` card. That figure is computed once in the backend — the same
number on the CFO dashboard — so quote it and never re-derive it: the FIGURES
rule forbids doing the `current_cash ÷ monthly_burn` division yourself, and a
second division would put two runway numbers in front of one user.

Read the card, not just its `amount`:

- **`amount` is MONTHS, not money** (`unit: "months"`). It arrives as a plain
  number, unlike the money cards' labelled envelopes — do not divide it, do not
  put a currency symbol on it.
- **`amount: null` means there is no runway clock**, not that it ran out. The
  company is not burning (a profitable or cash-flat month has unbounded runway)
  or cash could not be identified; `comparator` says which, and that sentence is
  what you report. Never say "no months left".
- `provisional: true` — the month is not closed, so say the figure can still move.
- `polarity` on the card is `neutral` by design: runway carries no delta.

The `burn` card beside it is the trailing-three-month average; the `cash` card is
the position. All three are one call, and they agree with each other by
construction because one builder produced them.

- The `burn` script below may print a client-side runway as a byproduct of the
  burn math — **do not present that number**; quote the KPI card instead.

## Cash drivers — rank by absolute impact

"What's draining cash?" = rank the operating **detail** rows (skip subtotals and
net-section rows, they'd double-count) by **absolute** amount, so the biggest
movers surface regardless of sign. The usual suspects: collections (row 6, the
inflow), payroll (16), and the COGS/R&D/S&M/G&A `ref` rows (8–13). For a top
driver, drill into its `breakdown` note (rows 62+, joined by `parent`) to name
the specific lines — or use `explain`/`drilldown`.

## Retrieve compactly

Cash-flow payloads are large and sparse (~200 rows, most zero). Fetch
**`density=summary`** — it returns the subtotal / net-section rows (operating /
investing / financing / total change), the `opening_cash` / `closing_cash` level
rows, and the `totals` / `tieout` blocks, each with its `row_num`, in a small
inline payload; the `ref` category rows, the per-category `breakdown` notes and
the `check` row drop out (ask for `density="detail"` — trimmed with `fields` — or
a `section` block — `operating | investing | financing`, the closed CF drill set —
when you need a line's composition). Don't add `compare` / `include_trend` /
`include_composition` for a validation pull. If a heavier pull spills to a file,
**don't read the raw JSON back** — use the shared CLI (relative paths from the
skill dir):

```bash
python scripts/lucid_utils.py totals <cf.json>
python scripts/lucid_utils.py rows <cf.json> --section operating --nonzero
```

### Monthly operating / investing / financing breakdown

`tieout.per_month` only gives the **net** cash change per month (classified vs
bank delta) — *not* the operating/investing/financing split. To get each month's
split, request the months explicitly and read the aligned per-row `series`:

```text
get_cash_flow_direct(company="ACME", period="2025-12",
                     periods="2025-01,2025-02, … ,2025-12", view="lucid")
```

Each row then carries a `series` aligned to your `periods` order. Read the
**net-section rows** for the monthly splits — operating (row 21), investing
(row 31), financing (row 39), and total change (row 41) — confirming row
numbers/labels against the response (they're configured per company). These rows
survive `density="summary"`, as do the `opening_cash` / `closing_cash` level rows,
so **one** `density="summary"` call gives you both the monthly split and the
monthly cash level. Either way, one `periods=` call beats twelve single-month calls.

Then run the burn / driver math (use it for **burn**; runway is temporarily
unavailable, so don't present any runway the script prints):

```bash
# average operating burn from explicit net_operating values
# (the script also prints a client-side runway — do NOT present it)
python scripts/burn_runway.py \
    burn --net-operating="-450000,-440000,-460000" --cash=8000000

# or from several single-period CF files (oldest..newest)
python scripts/burn_runway.py \
    burn --periods jan.json feb.json mar.json --cash=8000000

# rank cash drivers for one period
python scripts/burn_runway.py drivers mar.json --top 8
```

## Illustrative example — fictional company (Acme Inc.), synthetic figures

Resolve `ACME`, then `get_cash_flow_direct(company="ACME", period="2025-03")` and
`get_balance_sheet(company="ACME", period="2025-03")` for the cash position.
Synthetic figures (Mar 2025):

| Figure | Value |
|---|---|
| Net operating (`net_operating`) | **−$450,000** ← burn = +$450,000/mo |
| Net investing (`net_investing`) | −$30,000 (intercompany) |
| Net financing (`net_financing`) | $0 |
| Total change (`total_change`) | −$480,000 |
| Opening cash (`opening_cash_start`) | $8,480,000 |
| Closing cash (`closing_cash_end`) | $8,000,000 |
| Tie-out `period_delta` | **$0 ✓** |
| Cash pool total (`get_cash_composition`) | $8,000,000 |
| Runway (`get_status` `kpis`) | 18 months — quoted from the card, never divided out |

Top operating drivers (by |impact|): R&D −$240,000, Payroll −$170,000, G&A
−$70,000, Financial −$10,000; the lone inflow is Collections from customers
+$40,000.

**Cross-check:** `closing_cash_end` $8,000,000 == the balance sheet's
`totals.cash.amount` (cash is counted per cash account, so it need not equal any
balance-sheet row); the month's `total_change` is −$480,000.

**Runway:** quote the `runway` card from `get_status(sections=["kpis"])` beside
the cash position ($8.0M) and the ~$450K/mo operating burn. Do not divide the two
to produce your own month count — the card is the backend's number, and a second
division would put two runways in front of one reader. If the card's `amount` is
`null`, say what its `comparator` says (not burning, or cash unidentified) —
never "no months left".

**The financing nuance to call out:** Acme raised a **$3,000,000 SAFE** (it sits
on the balance sheet as a long-term liability; on the cash flow it's the
financing SAFE row). In a month where that raise lands, it's a financing
**inflow** that lifts total cash and makes "total change" look benign — but it
does **nothing** for operating burn. This is why "total change" is a misleading
proxy for burn: report the durable −$450,000 operating burn, not the
cash-flattering effect of the raise. Always surface this distinction so the burn
picture isn't misread.

## Answering

Follow the answer contract in `lucid-platform-guide`, applied to a cash read.

Tell it in this order: the cash position and its direction; the burn —
separating durable **operating** burn from the total cash change (the single most
important distinction here, since a financing inflow like a SAFE can flatter
total cash while operations bleed); the **runway**, quoted from the `get_status`
`kpis` card (when its `amount` is `null`, give its `comparator`'s reason — a month
that is not burning has no runway clock); what's draining cash (the top operating
drivers); and any one-off financing / investing events that moved cash but aren't
burn.

- **Quote** the closing cash (the cash flow's closing-cash figure — not a
  balance-sheet row, which can also hold accounts that are not cash), net
  operating / investing / financing and the total change, from the report.
- **Rank the drivers** — collections, payroll, the COGS / R&D / S&M / G&A lines —
  by absolute impact, using `scripts/burn_runway.py` for any trailing-window
  averages, and label those averages as derived ("3-month average operating burn").
- **Cash by currency or bank**: quote `get_cash_composition`'s subtotal rows
  (`closing_cash`, `total_cash_pool`, each `currency_subtotal`, per-bank rows at
  `density="detail"`) verbatim — never a total you summed yourself — and state
  the basis (figures in the reporting currency, *grouped by* each account's
  denomination, not native amounts).
- Close with 2–3 follow-ups such as "Break the operating burn into its top
  lines?", "Show the same split month by month?" or "Which accounts make up the
  cash pool?".

Quote the **runway** from `get_status(sections=["kpis"])` rather than computing
one — report it beside the cash position and the operating burn, and never divide
the two yourself (Lucid publishes runway precisely so it is computed once).
Read-only throughout; never add `compare` / `include_trend` to a *validation* pull
(a deliberate multi-month `periods=` pull is a different thing, and is one call).
Lead with the tie-out: if `period_delta ≠ 0` (cash flow) or `totals.tie_delta ≠ 0`
(cash composition), say so loudly and treat every cash figure as suspect.
