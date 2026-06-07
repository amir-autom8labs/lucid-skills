# Board-pack assembly checklist

Run top to bottom. The point is a pack where every number agrees and every
tie-out is green before anything is exported.

## Lock the basis (do once)
- [ ] Company resolved to a real `code` (`search_entities`/`list_entities`).
- [ ] One `period` chosen and stated (month vs quarter decided).
- [ ] `view` chosen (default `lucid`) and stated on the cover/header.
- [ ] Same company + period + view used for **every** pull — no mixing.

## Pull compactly (one pass, ≤5 reports)
- [ ] `get_dashboard`
- [ ] `get_pl` (+ `compare="mom"` for a month, `"qoq"`/`"yoy"` for a quarter — P&L only)
- [ ] `get_balance_sheet`
- [ ] `get_cash_flow_direct`
- [ ] `get_bva`
- [ ] No `include_trend` / `include_composition` anywhere (overflow).
- [ ] Spilled files read via `lucid_utils` CLI, not pasted into context.

## Assemble + reconcile
- [ ] Ran `scripts/board_pack.py` over the five payloads.
- [ ] **Cash** ties: dashboard == BS row 5 == CF closing_cash.
- [ ] **Net result** ties: P&L row 24 magnitude == BS row 55 magnitude.
- [ ] Tie-outs all OK: P&L/BVA `check_delta`, BS `balance_check_delta`,
      CF `period_delta`, dashboard `tie_out_ok`.
- [ ] Any MISMATCH is either fixed (wrong basis) or surfaced in Section 7 + exec summary.

## Structure (the 7 sections)
- [ ] 1 Executive summary (3–5 board-relevant bullets)
- [ ] 2 KPI scorecard (unit-aware)
- [ ] 3 P&L with prior-period column (headline rows)
- [ ] 4 Balance sheet (sign-flipped to magnitudes; flag negative equity)
- [ ] 5 Cash flow & runway
- [ ] 6 Budget vs actual (material variances)
- [ ] 7 Risks & flags (incl. any tie-out failure)

## Export
- [ ] Right document skill: `document-skills:xlsx` (workbook, one sheet/exhibit),
      `document-skills:pdf` / `md-to-pdf` (PDF), `document-skills:pptx` (deck),
      or filled-in `assets/board-pack-template.md` (markdown).
- [ ] Basis (company/period/view) printed on the pack.
- [ ] Did NOT reimplement document generation in this skill.
