---
name: workspace-status
description: >-
  Where things stand in a company's Lucid workspace right now — what's pending or
  waiting on the user, whether the reports can be trusted (report health and
  reconciliation checks), what changed recently, the headline KPI strip, and
  "can we close?". Use this WHENEVER the user asks "what's on the table", "what's
  pending", "what's waiting on me", "anything I should look at", "what changed",
  "what's new", "is everything OK with the books", "can we close {month}", or opens a
  session with no specific question. It reads Lucid's get_status (and
  get_close_readiness for a close verdict) and answers in plain business terms.
  For the financial RESULTS across statements ("how are we doing") use
  financial-position-review instead; for WHY a check is failing use
  investigate-data-issue. Builds on lucid-platform-guide.
---

# Workspace status

The operational front door to a company in Lucid: pending work, report health,
recent activity, and on request the headline KPIs and the month's biggest moves.
It answers *"where do things stand?"*, not *"how is the business doing?"* — that
is `financial-position-review`.

Read `lucid-platform-guide` first for entity resolution, periods and the answer
contract. The `get_status` tool description is detailed and authoritative on
every field; this skill covers when to call it and how to answer.

## Method

1. **Resolve the company** (`search_entities` / `list_entities`). If the user has
   access to several and named none, ask which one — or, for a session opener,
   offer the list.
2. **Recall the user's materiality preferences** (see below) and pass any you
   have as overrides.
3. **Call `get_status(company, ...)`** once. A plain call returns `pending`,
   `health` and `activity`. Add sections only when asked:
   - `sections=["kpis"]` — the headline KPI strip (cash, runway, revenue, gross
     margin, operating profit, net profit, burn), backend-computed, quoted verbatim;
   - `"moved"` — the month's largest changes and what is already known to be wrong;
   - `period=` to anchor a month other than the latest.
4. **"Can we close?"** → `get_close_readiness(companies=[...], period=...)`. It is
   the authoritative close verdict. Do not answer a close question from the
   `health` section: most of its checks are advisory and do not stop a close.
5. Anything the status turns up that needs explaining goes to the right skill:
   a failing check → `investigate-data-issue`; a figure to prove →
   `explain-and-audit`; how to do the fix in the app → `product-help`.

## Answering

Follow the answer contract in `lucid-platform-guide`. Lead with what needs the
user's attention, then the rest, briefly:

- **Pending** — counts are item counts, not money. Name the oldest or blocking
  items with who and how long, *only* where the tool gives them; where `actor` or
  `age_days` is null, say less rather than inventing it.
- **Health** — read each check's `state`, never `ok` alone. `fail` is a break;
  `warning` is within materiality; `not_applicable` is fine; **`not_evaluated`
  is "this was not checked"** — never "fine", never "failed". When one check
  `explains` another, report them as one finding led by the cause. Use the
  check's `title`, not its code, and quote its `detail` and breakdown amounts
  verbatim.
- **Activity** — the few changes that matter, not the whole feed.
- **Still in setup** — when `classification_pending` is present, the company is
  still being onboarded: say so, and that statements appear once the Classify
  step is finished. It is not a failure, and an empty KPI strip is not zero.
- Close with 2–3 follow-ups ("Why is the cash tie-out failing?", "Can we close
  September?", "Show the headline KPIs").

A bare greeting is not a status request: reply in one line and offer to check
where things stand.

## Materiality preferences

`get_status` accepts three per-user overrides for when things get flagged:

| Preference | Parameter |
|---|---|
| Unclassified movement that blocks, in dollars | `unclassified_blocking_usd` |
| Unclassified movement that blocks, as a % | `unclassified_blocking_pct` |
| Days a period may stay open before it is flagged | `open_period_days` |

- When the user sets one ("stop flagging unclassified under $50k"), pass it on
  the re-run and, if your Claude has memory, remember it as a **personal
  preference** (a threshold is not a financial fact, so it may live in personal
  memory). Without memory, say it applies to this conversation only.
- On later status checks, pass the remembered values silently; omit any you
  don't have, so Lucid's defaults apply. Never invent a threshold.
- A check's `detail` already credits a threshold to the user's own number —
  quote it, never restate or recompute the threshold.

## Constraints

- **Read-only.** You report; the user acts in the app.
- One `get_status` call per question; add `get_close_readiness` only for a close
  question.
- `health` covers the company's own statements; group-level controls belong to a
  consolidated report. Attribute a `scope: "group"` check to the group.
