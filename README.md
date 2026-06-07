# Lucid CFO plugin

A Claude plugin that turns Claude into a **CFO-grade analyst** on top of the
[Lucid](https://lucid.example) financial-data platform. It bundles the read-only
**Lucid MCP connector** with a set of skills that teach Claude how to consume
Lucid's data correctly and run the analyses a CFO actually asks for.

Everything is **read-only**. The connector forwards your Auth0 access token to the
Lucid backend, which enforces authorization and company-level row security — Claude
only ever sees the companies and periods you are granted.

## What's inside

| Skill | What it does |
|---|---|
| `lucid:lucid-platform-guide` | **Start here.** How to drive the Lucid MCP correctly — entities, period grammar, views, the money envelope, comparisons, tie-out discipline, payload-size handling, and report row maps. Every other skill builds on this. |
| `lucid:financial-position-review` | Monthly close / "how are we doing" — a dashboard-led, cross-statement health check with tie-out verification. |
| `lucid:pl-and-margin-analysis` | Income-statement deep dive: revenue, gross margin, OpEx burn, MoM/QoQ/YoY trends, common-size. |
| `lucid:cash-and-runway` | Direct cash flow, burn, and runway; what's driving cash in/out; reconciliation to the bank delta. |
| `lucid:budget-vs-actual` | Variance analysis: where you're off plan, by how much, and why — ranked by materiality. |
| `lucid:balance-sheet-review` | Liquidity, working capital, AR/AP, intercompany, equity — with the sign convention handled correctly. |
| `lucid:explain-and-audit` | Trace any number to its source: `explain` (derivation) and `drilldown` (journal lines), plus reconciliation checks. |
| `lucid:board-pack` | Assemble a board-ready narrative and export it to xlsx / pdf, pulling coherently across every report. |

A Python helper (`scripts/lucid_utils.py`) parses Lucid's money envelope, reads
large tool results, and builds common-size / variance / ratio tables so every
analysis skill computes numbers the same, correct way. `scripts/lucid_utils.py`
is the canonical source; each skill **bundles its own copy** under
`skills/<name>/scripts/lucid_utils.py` so it stays self-contained and works in any
runtime (Claude Code, cowork, or claude.ai, where only the skill's own files are
loaded). The helper is an **optimization** — when no code interpreter is
available, the skills parse the report JSON inline (the values are already
dollars; see `lucid-platform-guide`).

> Maintainers: `scripts/lucid_utils.py` is the source of truth. After editing it,
> re-sync the per-skill copies (e.g. `for d in skills/*/scripts; do [ -f "$d/lucid_utils.py" ] && cp scripts/lucid_utils.py "$d/"; done`).

## Install

### Claude Code / cowork

The plugin ships an `.mcp.json` declaring the remote Lucid connector, so installing
the plugin wires up both the skills and the connector.

```bash
# Try it without installing (point at this directory):
claude --plugin-dir /path/to/lucid-skills

# Or add it as a marketplace and install:
/plugin marketplace add /path/to/lucid-skills      # or a git URL
/plugin install lucid@lucid-skills
```

On first tool call Claude Code runs the OAuth flow (Auth0 Universal Login). Log in
as a user with Lucid access; the connector turns active and the report tools work.

### Claude.ai

1. Add the connector once: **Settings → Connectors → Add custom connector**
   (requires a paid plan). URL: `https://lucid-mcp-xnaw7oe2ga-uc.a.run.app/mcp`
   → log in via Auth0 → approve read-only access.
2. Add the **skills** (this plugin) from the plugin/marketplace UI.
3. In a new chat, enable the connector and the skills. Tip: in the first message
   say "use Lucid" so Claude reaches for the tools.

## Configure your endpoint

The bundled `.mcp.json` points at the Lucid MCP endpoint
(`https://lucid-mcp-xnaw7oe2ga-uc.a.run.app/mcp`). To target a different
environment, change the `url` in `.mcp.json` (Claude Code / cowork) or enter the
corresponding URL when adding the custom connector (Claude.ai). The connector
authenticates each user via Auth0 and is row-level scoped to what that user is
granted.

## Notes for the curious

- **Money is pre-formatted.** Every monetary field arrives as
  `{"amount": "1234567.89", "currency": "USD", "units": "major"}` — already in
  dollars. Never divide by 100. The shared helper parses these.
- **Tie-outs matter.** Every report carries a reconciliation check. The skills
  verify it before trusting a number, the way a controller would.
- **Reports can be large.** A full P&L is ~170 rows and can overflow a single tool
  result into a spilled file; the skills retrieve compactly and extract with `jq`/
  Python. See `lucid-platform-guide`.
