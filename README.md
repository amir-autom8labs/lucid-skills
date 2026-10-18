# Lucid plugin for Claude

Use **your own Claude** (Claude Code, Cowork or Claude.ai) as a CFO-grade analyst
on your **Lucid** books. The plugin bundles the read-only Lucid connector with
the same skills that power the Lucid assistant inside the app. You get the same
analysis and the same rules for quoting figures, in your own Claude setup.

Everything is **read-only**. You sign in with your Lucid account. Claude only
sees the companies and periods you can see in Lucid, and it can never change
anything.

## What you can ask

| Ask something like… | Skill that handles it |
|---|---|
| "Where do things stand?" · "What's waiting on me?" · "Can we close September?" | `lucid:workspace-status` |
| "How are we doing?" · "Give me the month-end review" | `lucid:financial-position-review` |
| "Why did gross margin drop?" · "Show OpEx as % of revenue" | `lucid:pl-and-margin-analysis` |
| "What's our runway?" · "Where did the cash go?" | `lucid:cash-and-runway` |
| "Are we on budget?" | `lucid:budget-vs-actual` |
| "What's our working capital?" · "How much do we owe?" | `lucid:balance-sheet-review` |
| "Why is this number what it is?" · "Show me the entries behind it" | `lucid:explain-and-audit` |
| "Why is this check failing?" · "Why is this account on that line?" | `lucid:investigate-data-issue` |
| "How do I import journal entries?" · "Where do I close a period?" | `lucid:product-help` |
| "Build the board pack for Q3" | `lucid:board-pack` |

`lucid:lucid-platform-guide` is the foundation the others build on. It covers
choosing the company, period and view, reading figures, the tie-out checks, and
how to answer: quote figures exactly as Lucid reports them, disclose projected
amounts, and label anything derived.

## Install

### Claude Code / Cowork

The plugin ships an `.mcp.json` that connects to Lucid, so installing it sets up
both the skills and the connector.

```bash
/plugin marketplace add amir-autom8labs/lucid-skills
/plugin install lucid@lucid-skills
```

On the first Lucid tool call, Claude opens a browser to sign in to Lucid.

### Claude.ai

1. Add the connector once: **Settings → Connectors → Add custom connector**
   (paid plans). URL: `https://lucid-mcp-fmrq47kzya-uc.a.run.app/mcp`. Sign in
   with your Lucid account and approve read-only access.
2. Add the skills from this repository (each folder under `skills/` is one skill).
3. In a chat, enable the connector. Saying "use Lucid" in your first message
   helps Claude reach for it.

## How it differs from the in-app assistant

The analysis, checks and tools are the same. A few things work differently:

- **Figures are written into the answer.** In the app, figures appear in
  interactive blocks next to the reply. Here Claude quotes them in the text and
  tables exactly as Lucid reports them. Anything derived (a ratio Lucid doesn't
  publish, a share of total) is computed with the bundled scripts and labelled.
- **Screens are named by menu path** (e.g. "Work → Cash accounts") instead of
  in-app buttons.
- **Memory is your Claude's memory**, if you have it enabled. The skills tell
  Claude to keep personal preferences (report names, thresholds) separate from
  company figures, which should never land in memory that follows you across
  unrelated chats.
- **Exports** go through whatever pdf / pptx / xlsx skills your Claude has.

## Helper scripts

Each analysis skill bundles `scripts/lucid_utils.py` (money parsing, tie-out
status, identity-based row lookup, ratios) plus a skill-specific script. Claude
runs them when it has code execution. Without it, the skills read the report
JSON directly. `scripts/lucid_utils.py` at the root is the canonical copy. See
[MAINTAINING.md](MAINTAINING.md).

## Notes

- **Money arrives in dollars** (major units) as
  `{"amount": "1234567.89", "currency": "USD", "units": "major"}`. Never divide by 100.
- **Tie-outs come first.** Every report carries a reconciliation check, and the
  skills verify it before relying on a number.
- **Projected entries.** In an open month, Lucid's default view fills recurring
  costs that aren't booked yet with projected entries. The skills always say how
  much of a figure is projected.
- **Budget vs actual** is not yet available in Lucid. The skill says so rather
  than inventing variances.
