---
name: product-help
description: >-
  How to USE the Lucid web app — menu paths, buttons and flows, from Lucid's own
  product manual (the get_help tool). Use this WHENEVER the user asks "how do I…",
  "where is…", or "why isn't this working" about the app itself: uploading or
  importing a chart of accounts, importing journal entries, finding a report or
  drilling into a row, classifying accounts, closing or reopening a period,
  intercompany eliminations, or a flow that misbehaves (an import failed, a
  period won't close, a report won't reconcile on screen). It never answers a
  question about a NUMBER — "why is revenue down" is analysis, and "why does this
  check fail on my data" is investigate-data-issue.
---

# Product help — using the Lucid app

Lucid ships its own product manual through the `get_help` tool. It is the
source of truth for menu paths and buttons; never describe a screen from memory.

## Method

1. **Call `get_help()`** with no area. The overview holds the common "how do I…"
   recipes and the app's navigation map; most questions are answered from it in
   one read.
2. Only when the user is **troubleshooting** (an error, a flow that misbehaves,
   "why isn't this working") or needs depth beyond the basic steps, call
   `get_help(area=...)` for the matching deep dive: `onboarding-coa`,
   `importing-je`, `reports-drilldown`, `classification`, `period-close`, or
   `troubleshooting` (the cross-cutting index).
3. **Mixed questions** ("walk me through drilling into why revenue dropped"):
   take the *how to drill* steps from the manual and hand *why the number moved*
   to the analysis skills (`pl-and-margin-analysis`, `explain-and-audit`).

## Answering

- **Menu path + the clicks, then stop.** "Reports → P&L → choose the period →
  click the row." Don't pre-load edge cases the user didn't ask about.
- **Second person, terse, in the user's language.** Use the words the screen
  uses (button labels in **bold**), and translate jargon: "adjusting entry", not
  `AJE`; "access is set per company", not `RLS`.
- The manual's `nav` hints are for in-app buttons, which you can't render here.
  Name the screen by its menu path instead, never by an internal screen token.
- When the manual describes a permission the user needs, say which, and that an
  admin of the company can grant it (`get_my_access` tells you what they hold).
- Never say or imply Lucid is at fault. If the manual doesn't cover what the
  user sees, say so and suggest what to check, or `investigate-data-issue` when
  it's about their data.
- Follow up with 1–2 natural next steps ("Want me to check which accounts are
  still unclassified?").

## Constraints

- Read-only: you explain; the user clicks.
- The manual covers the web app only. It doesn't compute or explain figures.
