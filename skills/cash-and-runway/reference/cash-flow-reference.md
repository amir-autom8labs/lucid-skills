# Cash-flow reference — rows, tie-out, and burn/runway recipes

Companion detail for `cash-and-runway`. The canonical row maps and response
shapes live in `lucid:lucid-platform-guide` → `reference/report-reference.md`;
this file is the cash-specific cut plus worked recipes. Read the platform guide
for the money envelope, view modes, and payload handling.

## Direct cash-flow `row_type` semantics

`get_cash_flow_direct` rows carry both a `section` and a `row_type`. The
`row_type` tells you what a row *is*, which is how you avoid double-counting:

| `row_type` | Meaning | Use it for |
|---|---|---|
| `header` | Section label, amount 0 | Ignore in math |
| `detail_cf_class` | A classified cash line | Driver ranking |
| `detail_tb_ay` | A balance-sheet-account change in cash terms | Driver ranking |
| `ref` | Category headline (rows 8–13), totals its breakdown note via `group_key` | Driver ranking (don't also count its breakdown rows) |
| `subtotal` | Section subtotal (e.g. row 19) | Read, don't re-sum |
| `net_section` | Net per activity (rows 21/31/39) | Headline burn / activity totals |
| `grand_total` | Total change in cash (row 41) | Headline |
| `opening_cash` / `closing_cash` | Rows 43 / 44 | Position |
| `check` | Row 45, should be 0 | Sanity |
| `other_formula` | Projection / memo formulas (rows 48–60) | Usually ignore |
| `unclassified` | Row 9999 "Other" | **Non-zero = lines escaped classification — flag it** |

`section` ∈ `operating | investing | financing | meta | breakdown | other`.
The `breakdown` section (rows 62+) holds per-line note detail; each breakdown row
has `parent` = the `group_key` of its `ref` row, so you can expand "R&D" into its
constituent lines without a second tool call.

## Full row map (direct method)

Row numbers and line labels below are **illustrative** — they are configured per
company in the connector's report mapping (see `lucid:lucid-platform-guide` →
`reference/report-reference.md`). Prefer the stable `totals.*` keys
(`net_operating`, `total_change`, `opening_cash_start`, `closing_cash_end`) for
headline figures; treat specific row numbers as examples, not constants.

| Row | Section | Line (generic category) |
|---|---|---|
| 5 | operating | Operating activities (header) |
| 6 | operating | Collections from customers (inflow) |
| 8 | operating | COGS (ref) |
| 9 | operating | R&D (ref) |
| 10 | operating | Sales & marketing (ref) |
| 11 | operating | General & administrative (ref) |
| 12 | operating | Financial expense / (income) (ref) |
| 13 | operating | Other expense / (income) (ref) |
| 14 | operating | Income taxes |
| 15 | operating | Change in credit-card payables |
| 16 | operating | Payroll and payroll-related |
| 17 | operating | Withholding / payroll authorities |
| 18 | operating | Indirect / sales tax (VAT) |
| 19 | operating | Total expenses paid in cash (subtotal) |
| **21** | operating | **Net cash — operating** (net_section) |
| 24–30 | investing | Restricted/ST/LT deposits, PP&E, leasehold, **Intercompany (29)**, equity-in-earnings |
| **31** | investing | **Net cash — investing** (net_section) |
| 34 | financing | Short-term loans |
| 35 | financing | Fund raising — exercise of options |
| 36 | financing | Fund raising — **SAFE** |
| 37 | financing | Fund raising — equity |
| 38 | financing | Fund raising — equity issuance expenses |
| **39** | financing | **Net cash — financing** (net_section) |
| **41** | meta | **Total increase/(decrease) in cash** (grand_total) |
| 43 | meta | Cash at beginning of period (opening_cash) |
| 44 | meta | Cash at end of period (closing_cash) |
| 45 | meta | Check (should be 0) |
| 62+ | breakdown | Per-category note detail (parent/group_key) |
| 9999 | operating | Other / unclassified |

Note: a **SAFE** typically also appears on the **balance sheet** as a long-term
liability. On the cash flow it's the financing SAFE row when the cash lands.

## Tie-out walkthrough

The `tieout` block proves classified cash flow equals the real bank-balance
change:

```json
"tieout": {
  "per_month": [{"month": "mar",
                 "classified": {"amount": "-480000.00", ...},
                 "bank_delta": {"amount": "-480000.00", ...},
                 "delta":      {"amount": "0.00", ...}}],
  "classified_total": {"amount": "-480000.00", ...},
  "bank_delta_total": {"amount": "-480000.00", ...},
  "period_delta":     {"amount": "0.00", ...}
}
```

Checklist before presenting any cash number:

1. `tieout.period_delta == 0` — overall classified flow == bank delta.
2. Every `tieout.per_month[].delta == 0` — no single month is off.
3. Row 45 `check == 0` and row 9999 `unclassified == 0`.
4. Internal consistency: row 41 `total_change` == row 21 + row 31 + row 39, and
   == row 44 − row 43.

If any fails, lead with the discrepancy. A non-zero `period_delta` means the
books don't reconcile to the bank — the figures are not trustworthy yet.

## Burn / runway recipe

```
operating_burn_month = -net_operating            # outflow -> positive burn
avg_burn             = mean(operating_burn over trailing 3–6 months)
runway_months        = current_cash / avg_burn   # None if avg_burn <= 0
```

- **current_cash**: closing cash (CF row 44), the dashboard cash KPI, or balance
  sheet row 5 — they should agree at a period end.
- **Operating vs total**: burn off `net_operating`, never off `total_change`
  (which mixes in financing/investing one-offs like a SAFE raise).
- **Unbounded**: burn ≤ 0 (a cash-generating month) → runway is `None`/unbounded,
  matching Lucid's runway KPI returning `null` when EBITDA ≥ 0.
- **Dashboard vs CF runway**: the dashboard KPI uses an EBITDA-based burn; a
  direct-CF burn includes working-capital timing. Expect them to differ; report
  both with their basis rather than reconciling them.

## Script

`scripts/burn_runway.py` (stdlib + `lucid_utils` via `CLAUDE_PLUGIN_ROOT`):

- `burn --periods a.json b.json c.json --cash N` — pulls `totals.net_operating`
  from each single-period CF file, averages the burn, derives runway.
- `burn --net-operating="-450000,-440000,-460000" --cash N` — same from raw
  values.
- `drivers cf.json --top N` — ranks operating detail rows by |cash impact|.

Skips `None`/no-data months rather than treating them as zero, so a gap in the
books doesn't understate burn.
