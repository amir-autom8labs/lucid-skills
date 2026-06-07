---
name: cash-and-runway
description: >-
  Cash position, burn rate, and runway analysis from the Lucid CFO connector —
  use this WHENEVER someone asks "how much cash do we have", "what's our
  runway", "what's our burn rate", "how many months of cash left", "are we
  running out of money", "what's draining cash", "where did the cash go",
  "cash position", or any cash-flow question. It pulls the direct-method cash
  flow (get_cash_flow_direct), the dashboard cash + runway KPIs (get_dashboard),
  and the balance-sheet cash line, verifies the mandatory cash-flow tie-out
  (classified flow == bank-balance delta), separates durable operating burn from
  one-off financing/investing swings (e.g. a SAFE raise that flatters total
  cash), ranks what's driving cash in and out, and computes runway from a
  trailing burn window. Read lucid:lucid-platform-guide first for the shared
  mechanics this builds on.
---

# Cash & runway

Answer the four questions a founder loses sleep over: **How much cash do we
have? How fast are we spending it? How long does it last? What's eating it?**
This skill leans on `lucid:lucid-platform-guide` for the connector mechanics
(entity resolution, period grammar, view modes, the money envelope, payload
spilling, the shared helper). Read that first. Here we focus on the cash-specific
reasoning that's easy to get wrong.

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

## The three sources

| Need | Tool | Key fields |
|---|---|---|
| Burn composition + drivers + tie-out | `get_cash_flow_direct` | `totals`, `rows`, `tieout` |
| Cash KPI + Lucid's own runway number | `get_dashboard` | `kpis` (cash, runway) |
| Cash on the books at period end | `get_balance_sheet` | row 5 (Cash and Cash equivalents) |

Default `view="lucid"`, default to a single recent month, and resolve the
company with `search_entities` first (never guess a handle). Keep it to **≤2
single-period calls** to sanity-check — the worked numbers below are already
validated.

## Direct cash-flow structure

`get_cash_flow_direct` is the spine. The numbers you cite live in named rows
**and** in the `totals` block (use either; they agree). Row numbers and labels
below are **illustrative** — they're configured per company in the report mapping
(see `lucid:lucid-platform-guide` → `reference/report-reference.md`); prefer the
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
quirk to paper over. Also glance at row 45 (`check`) and any row `9999`
("Other / unclassified") — non-zero there means lines fell outside the
classification map. A controller signs off the reconciliation before presenting;
so do you.

## Burn rate — operating, over a trailing window

Burn is how fast cash is consumed: **burn = −net_operating** (a −$450,000
operating month is +$450,000 of burn). One month is noisy (timing of payroll
runs, large vendor payments), so compute an **average over a trailing window**
(3–6 months). To get several months of operating cash flow, either:

- pull a wider period (`FY2025`, `2025-Q1`) — cash flow is a **flow**, so a
  quarter sums its months for you; or
- pull a few single months and feed their `net_operating` into the script.

Don't sum single-month balance-sheet cash yourself — use the flow report.

## Runway — current cash ÷ monthly operating burn

```
runway_months = current_cash / average_monthly_operating_burn
```

State the method explicitly ("17 months at the trailing-3-month operating
burn"). Two things to know:

- **When not burning, runway is unbounded.** `runway_months()` in the helper
  returns `None` when burn ≤ 0, mirroring **Lucid's own runway KPI, which
  returns `null` when EBITDA ≥ 0** (a profitable month has no runway clock).
- **Your computed runway can differ from the dashboard's `runway` KPI** and
  that's expected — the dashboard derives its months from an EBITDA-based burn,
  while a direct-CF operating burn includes working-capital timing. Report the
  dashboard KPI *and* your CF-based figure, and explain the basis of each rather
  than forcing them to match.

## Cash drivers — rank by absolute impact

"What's draining cash?" = rank the operating **detail** rows (skip subtotals and
net-section rows, they'd double-count) by **absolute** amount, so the biggest
movers surface regardless of sign. The usual suspects: collections (row 6, the
inflow), payroll (16), and the COGS/R&D/S&M/G&A `ref` rows (8–13). For a top
driver, drill into its `breakdown` note (rows 62+, joined by `parent`) to name
the specific lines — or use `explain`/`drilldown` from the platform guide.

## Retrieve compactly

Cash-flow payloads are large and sparse (~200 rows, most zero). Ask for one
period, don't add `compare` / `include_trend` / `include_composition` for a
validation pull. When a result spills to a file, **don't read the raw JSON
back** — use the shared CLI:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/lucid_utils.py totals <cf.json>
python ${CLAUDE_PLUGIN_ROOT}/scripts/lucid_utils.py rows <cf.json> --section operating --nonzero
```

Then run the burn/runway/driver math:

```bash
# average operating burn + runway from explicit net_operating values
python ${CLAUDE_PLUGIN_ROOT}/skills/cash-and-runway/scripts/burn_runway.py \
    burn --net-operating="-450000,-440000,-460000" --cash=8000000

# or from several single-period CF files (oldest..newest)
python ${CLAUDE_PLUGIN_ROOT}/skills/cash-and-runway/scripts/burn_runway.py \
    burn --periods jan.json feb.json mar.json --cash=8000000

# rank cash drivers for one period
python ${CLAUDE_PLUGIN_ROOT}/skills/cash-and-runway/scripts/burn_runway.py \
    drivers mar.json --top 8
```

## Illustrative example — fictional company (Acme Inc.), synthetic figures

Resolve `ACME`, then `get_cash_flow_direct(company="ACME", period="2025-03")` and
`get_dashboard(company="ACME", period="2025-03")`. Synthetic figures (Mar 2025):

| Figure | Value |
|---|---|
| Net operating (`net_operating`) | **−$450,000** ← burn = +$450,000/mo |
| Net investing (`net_investing`) | −$30,000 (intercompany) |
| Net financing (`net_financing`) | $0 |
| Total change (`total_change`) | −$480,000 |
| Opening cash (`opening_cash_start`) | $8,480,000 |
| Closing cash (`closing_cash_end`) | $8,000,000 |
| Tie-out `period_delta` | **$0 ✓** |
| Dashboard — Cash | $8,000,000 (Δ −$480,000 vs Feb) |
| Dashboard — Runway | **14 months** (at current EBITDA-based burn) |

Top operating drivers (by |impact|): R&D −$240,000, Payroll −$170,000, G&A
−$70,000, Financial −$10,000; the lone inflow is Collections from customers
+$40,000.

**Cross-check:** `total_change` −$480,000 == dashboard cash Δ; `closing_cash_end`
$8,000,000 == dashboard cash.

**Runway, two bases:** the CF operating runway ≈ cash $8.0M ÷ ~$450K/mo operating
burn ≈ **~17.8 months**, which legitimately differs from the dashboard's
EBITDA-based runway KPI (**14 months**). Report both with their basis rather than
forcing them to agree.

**The financing nuance to call out:** Acme raised a **$3,000,000 SAFE** (it sits
on the balance sheet as a long-term liability; on the cash flow it's the
financing SAFE row). In a month where that raise lands, it's a financing
**inflow** that lifts total cash and makes "total change" look benign — but it
does **nothing** for operating burn. Runway must be built on the −$450,000
operating burn, not on the cash-flattering effect of the raise. Always surface
this distinction so the runway number isn't misread.

## Output structure

Lead with the answer, then show your work, in this order:

1. **Cash position** — closing cash (row 44 / dashboard cash KPI) + Δ vs prior.
2. **Burn** — operating burn (the durable number) *and* total cash change,
   clearly labelled as different things.
3. **Runway** — months, with the **method stated** (window + which burn basis);
   note `null`/unbounded when not burning, and reconcile vs the dashboard KPI.
4. **Top cash drivers** — ranked operating in/out lines.
5. **Financing / investing events** — one-offs (SAFE, equity, intercompany)
   that moved cash but aren't burn.
6. **Tie-out** — state `period_delta == 0` (or flag it loudly if not).

Read-only throughout. Never use `compare` / `include_trend` for the tie-out
validation pull; prefer the validated numbers and the shared helper.
