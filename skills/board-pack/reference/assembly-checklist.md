# Board-pack assembly checklist

Run top to bottom. The point is a pack where every number agrees and every
tie-out is green before anything is exported.

## Lock the basis (do once)
- [ ] Company resolved to a real `code` (`search_entities`/`list_entities`).
- [ ] One `period` chosen and stated (month vs quarter decided).
- [ ] `view` chosen (default `lucid`) and stated on the cover/header.
- [ ] Same company + period + view used for **every** pull — no mixing.

## Pull compactly (one pass, four statements)
- [ ] `get_pl` (+ `compare="mom"` for a month, `"qoq"`/`"yoy"` for a quarter — P&L only)
- [ ] `get_balance_sheet`
- [ ] `get_cash_flow_direct`
- [ ] `get_trial_balance` (if the pack includes a TB exhibit)
- [ ] `get_status(sections=["kpis"])` for the KPI scorecard — the backend-computed
      strip (cash · runway · revenue · gross margin · operating profit · net profit
      · burn). Quote the cards; never re-derive one off a statement. Do NOT call
      `get_dashboard` — that tool stays withdrawn.
- [ ] Do NOT rely on `get_bva` — it returns a "not available yet" stub; note that
      budget-vs-actual isn't available yet rather than showing variance numbers.
- [ ] No `include_trend` / `include_composition` anywhere (overflow).
- [ ] Spilled files read via `lucid_utils` CLI, not pasted into context.

## Assemble + reconcile
- [ ] Ran `scripts/board_pack.py` over the statement payloads.
- [ ] **Cash** ties: BS `totals.cash.amount` == CF `totals.closing_cash_end`
      (== `get_cash_composition` where pulled). Bind to the `totals.cash` block,
      NEVER to a balance-sheet row — cash is counted per cash account, so it
      need not equal any row, and a row number names whichever asset the
      company's routing put first.
- [ ] If BS `totals.cash.unresolved_reason` is set, the cash tie is **not
      evaluated**: say so and quote the reason. Do not print `0`, and do not
      let a two-way check stand in silently for a three-way one.
- [ ] If BS `totals.cash.disclosures` is non-empty, part of the cash is
      presented outside a cash class ("includes …"), or a cash class also
      holds accounts that are not cash ("excludes …"). **Every clause appears
      beside the cash figure in the deck, and so does the reconciliation line
      of each "includes" clause ("of which $X presented under <class>", the
      sheet's `reconciliation` column).** An "excludes" clause has no
      reconciliation line — the data carries no amount for it — and appears on
      its own.
      The figure itself is right; do not subtract that part, and do not add the
      other class's balance-sheet row to cash.
- [ ] **Net result** ties: P&L `role: net_profit` magnitude == BS
      `role: pl_loss_profit` magnitude. Bind to the roles, not to row numbers.
- [ ] Tie-outs all OK: P&L `check_delta`, BS `balance_check_delta`,
      CF `period_delta`, trial balance `balance_check_delta`.
- [ ] Any MISMATCH is either fixed (wrong basis) or surfaced in Section 7 + exec summary.

## Structure (the 7 sections)
- [ ] 1 Executive summary (3–5 board-relevant bullets)
- [ ] 2 KPI scorecard — the `get_status` `kpis` cards, quoted verbatim
      (`runway` in months, `gross_margin` in basis points, a `null` amount
      reported with its `comparator`'s reason, a `provisional` month labelled)
- [ ] 3 P&L with prior-period column (headline rows)
- [ ] 4 Balance sheet (sign-flipped to magnitudes; flag negative equity)
- [ ] 5 Cash flow (operating/investing/financing nets, total change, closing cash);
      runway is quoted from the §2 KPI card, never divided out of these figures
- [ ] 6 Budget vs actual — **temporarily unavailable** (`get_bva` stub); note it
- [ ] 7 Risks & flags (incl. any tie-out failure)

## Export
- [ ] Right document skill: `document-skills:pdf` / `md-to-pdf` (PDF),
      `document-skills:pptx` (deck),
      or filled-in `assets/board-pack-template.md` (markdown).
- [ ] Basis (company/period/view) printed on the pack.
- [ ] Did NOT reimplement document generation in this skill.
