# Maintaining this plugin

This is the **public** build of the Lucid plugin. The in-app Lucid assistant
runs from a private copy of the same skills, kept in the Lucid monorepo under
`companion/skills-plugin/`. That copy is the upstream: analysis logic, tool
usage, checks and scripts change there first.

## What is different here (keep it on every refresh)

The in-app assistant has machinery that does not exist in a user's own Claude,
so a refresh is **not** a plain copy. These parts are public-only:

| Area | In-app copy | Public copy |
|---|---|---|
| Answer contract (`lucid-platform-guide`) | narrative only; figures nominated as blocks/metrics and computed server-side | figures quoted verbatim in the answer; derived figures computed with the bundled scripts and labelled |
| Each skill's `## Answering` section | `present_answer` / block / metric nominations | quoted figures, scripts for derived ones, 2–3 follow-ups |
| Routing, voice, "never blame Lucid", memory rules | the assistant's system prompt | `lucid-platform-guide` (*answer contract*, *which skill*) |
| Screens | `navigation` blocks rendered as buttons | menu paths ("Work → Cash accounts") |
| `workspace-status`, `product-help` | no skill; the system prompt routes to the tools | public-only skills |
| `board-pack` exports | the assistant's own pdf skill | whatever document skills the user has |
| `.mcp.json` | stage/prod per deployment | **prod** endpoint |

## Refresh procedure

1. Diff upstream against this repo, skill by skill
   (`diff -ru <monorepo>/companion/skills-plugin/skills skills`).
2. Bring over everything except the public-only parts above: method, tool
   parameters, checks, pitfalls, reference files, scripts.
3. Copy `scripts/lucid_utils.py` and sync the per-skill copies:
   `for d in skills/*/scripts; do [ -f "$d/lucid_utils.py" ] && cp scripts/lucid_utils.py "$d/"; done`
4. Re-apply the public adaptations to any `## Answering` section that changed.
5. Run the confidentiality scan below, then type check:
   `uvx ty check` (uses `ty.toml`).
6. Bump `version` in `.claude-plugin/plugin.json` **and**
   `.claude-plugin/marketplace.json`.

## Confidentiality scan — must print nothing

This repository is public. No ticket IDs, customer or partner names or codes,
real figures, internal hostnames other than the public MCP endpoint, or
in-app-only mechanics.

```bash
grep -rnE "CU-[a-z0-9]{6,}|present_answer|/mnt/memory|nominat(e|ion)s? .*block|design partner|xnaw7oe2ga|₪[0-9]" \
  --exclude-dir=.git --exclude=MAINTAINING.md .
```

Use the fictional **Acme Inc. (`ACME`)** with round synthetic figures for
examples. Never use a real company's code, account names or numbers.
