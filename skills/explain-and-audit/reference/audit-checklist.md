# Audit checklist — checks to run before trusting a number

Run these in order. Stop and surface the problem the moment a check fails; never
present a clean-looking explanation over a failed reconciliation.

## 0. You're pointed at the right cell

- [ ] Company handle resolved via `search_entities` (not guessed). For a group,
      the parent (`is_root: true`, e.g. `ACME`) and a sub (e.g. `ACME-US`) carry
      different numbers — confirm which one the user means.
- [ ] `report` / `period` / `row_num` / `column` match what the user is looking
      at. `row_num` was read from the report response (`rows[]` carry `row_num` +
      `label`) and is per-company — not from memory.
- [ ] `view` chosen deliberately. Default `lucid` (ledger + adjustments). If the
      user's number came from raw bookkeeping, also pull `base`/`erp_only` — the
      gap is the AJEs.

## 1. The cell reconciles to its lines (the core check)

- [ ] **`drilldown` → `sum_matches_cell: true`.** This is non-negotiable: it
      proves `je_total_sum + aje_total_sum == cell_value`. If `false`, the figure
      is suspect (something unclassified or the books don't tie at this cell) —
      say so prominently and stop.
- [ ] `je_total_sum` and `aje_total_sum` are population totals; reconcile against
      these, not the sampled `je_lines` / `aje_lines` you happened to page in.
- [ ] If `je_next_cursor` / `aje_next_cursor` are non-null and the user wants
      every line, page through (independent cursors, `limit` 1–200) — but the
      totals already cover the full population for the reconciliation.

## 2. The story matches the lines

- [ ] `explain.formula.expression` is the operation you're describing.
- [ ] `explain.accounts` (signed) and `explain.controller_entries` line up with
      the `drilldown` JE / AJE lines — same accounts, same direction. A revenue
      account contributes **negative** to a margin; a cost contributes positive.
- [ ] Every Controller-Layer entry you cite is `state: "approved"`. Flag any that
      are draft/pending — those aren't close-ready.
- [ ] Non-English descriptions quoted verbatim (optionally glossed), never
      silently translated or dropped.

## 3. The host report ties out (whole-statement check)

The cell can reconcile while the statement around it doesn't. Confirm the report's
own tie-out (see `lucid:lucid-platform-guide` for where each lives):

- [ ] Trial balance / Balance sheet: `totals.balance_check_delta == 0`
- [ ] P&L / BVA: `totals.check_delta == 0`
- [ ] Cash flow: `tieout.period_delta == 0`
- [ ] Dashboard: `tie_out_ok == true`

A non-zero check is a books problem worth surfacing, not something to paper over.

## 4. Cross-foot the explanation

- [ ] The contributing accounts + adjustments you cite actually sum to the cell
      (`Σ ledger net + Σ aje net == cell_value`). This is the same arithmetic
      `sum_matches_cell` guarantees — do it visibly when you present, so the
      reader can follow the bridge from ledger → adjustments → reported figure.
- [ ] State the **view** alongside the number. The same cell is a different value
      under `base` vs `lucid`; an unlabeled figure is unverifiable.

## Verdict template

> **<Label> (<report> row <n>), <period>, <view> view: <value>.**
> Formula: <expression>. Ledger Σ <je_total_sum> + adjustments Σ <aje_total_sum> =
> <cell_value>. **Reconciled — sum_matches_cell: true.** Report tie-out: <delta/OK>.

If any box is unchecked, lead with the failure, not the number.
