# Board Pack — {{COMPANY_NAME}} ({{COMPANY_CODE}})

**Period:** {{PERIOD_LABEL}}  |  **View:** {{VIEW}}  |  **Currency:** {{CURRENCY}}
**Prepared:** {{GENERATED_AT}}  |  Source: Lucid CFO platform (read-only)

> All figures are on the {{VIEW}} (close-ready) basis for {{PERIOD_LABEL}}.
> Liabilities and equity are shown as positive magnitudes.

---

## 1. Executive summary

- **Cash & runway:** {{CASH}} on hand; ~{{RUNWAY}} of runway at current burn.
- **Revenue:** {{REVENUE}} ({{REVENUE_COMPARATOR}}).
- **Gross margin:** {{GROSS_MARGIN_PCT}}.
- **Net result:** {{NET_PROFIT}} for the period.
- **Top risk / change:** {{TOP_RISK}}

---

## 2. KPI scorecard

| KPI | Value | vs prior |
|---|---|---|
| Cash | {{CASH}} | {{CASH_DELTA}} |
| Runway | {{RUNWAY}} | {{RUNWAY_COMPARATOR}} |
| Revenue (QTD) | {{REVENUE}} | {{REVENUE_DELTA}} |
| Gross margin | {{GROSS_MARGIN_PCT}} | {{GM_DELTA}} |

---

## 3. Profit & Loss — {{PERIOD_LABEL}} vs {{PRIOR_PERIOD_LABEL}}

| Line | {{PERIOD_LABEL}} | {{PRIOR_PERIOD_LABEL}} | Δ |
|---|---|---|---|
| Revenues | {{PL_REVENUE}} | {{PL_REVENUE_PRIOR}} | {{PL_REVENUE_DELTA}} |
| COGS | {{PL_COGS}} | | |
| **Gross margin** | **{{PL_GROSS_MARGIN}}** | | |
| % Gross margin | {{GROSS_MARGIN_PCT}} | | |
| Total operating expenses | {{PL_OPEX}} | | |
| **Operating income / (loss)** | **{{PL_OPERATING_INCOME}}** | | |
| **Net profit / (loss)** | **{{NET_PROFIT}}** | {{NET_PROFIT_PRIOR}} | {{NET_PROFIT_DELTA}} |
| EBITDA | {{PL_EBITDA}} | | |

Tie-out: P&L `check_delta` = {{PL_CHECK}} — {{PL_TIEOUT}}

---

## 4. Balance sheet (magnitudes) — as of {{PERIOD_END}}

| Assets | | Liabilities & equity | |
|---|---|---|---|
| Cash & equivalents | {{BS_CASH}} | Accounts payable | {{BS_AP}} |
| Accounts receivable | {{BS_AR}} | Total current liabilities | {{BS_TCL}} |
| Total current assets | {{BS_TCA}} | Total long-term liabilities | {{BS_TLTL}} |
| **TOTAL ASSETS** | **{{TOTAL_ASSETS}}** | **Total equity** | **{{TOTAL_EQUITY}}** {{EQUITY_FLAG}} |

Tie-out: `balance_check_delta` = {{BS_CHECK}} — {{BS_TIEOUT}}

---

## 5. Cash flow & runway — {{PERIOD_LABEL}}

| Section | Amount |
|---|---|
| Net cash — operating | {{CF_OPERATING}} |
| Net cash — investing | {{CF_INVESTING}} |
| Net cash — financing | {{CF_FINANCING}} |
| **Total increase / (decrease) in cash** | **{{CF_TOTAL_CHANGE}}** |
| Cash at beginning of period | {{CF_OPENING}} |
| Cash at end of period | {{CF_CLOSING}} |

Monthly burn: {{MONTHLY_BURN}}  |  Runway: {{RUNWAY}}
Tie-out: cash flow `period_delta` = {{CF_CHECK}} — {{CF_TIEOUT}}

---

## 6. Budget vs actual — material variances

| Line | Actual | Budget | Variance | % |
|---|---|---|---|---|
{{BVA_ROWS}}

Tie-out: BVA `check_delta` = {{BVA_CHECK}} — {{BVA_TIEOUT}}

---

## 7. Risks & flags

- **Cross-statement reconciliation:** {{RECONCILIATION_STATUS}}
  - Cash: dashboard {{CASH}} == BS row 5 {{BS_CASH}} == CF closing {{CF_CLOSING}} — {{CASH_RECON}}
  - Net result: P&L net {{NET_PROFIT}} vs BS current-year P&L {{BS_CURRENT_YEAR_PL}} — {{NET_RECON}}
- **Tie-outs:** {{TIEOUT_SUMMARY}}
- **Other flags:** {{OTHER_FLAGS}}
