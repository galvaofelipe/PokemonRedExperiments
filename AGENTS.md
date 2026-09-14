# AGENTS.md

## Code search

The codegraph MCP (local index in `.codegraph/`, untracked) is available to agents in this repo and is better than Grep/Glob for navigating code (definitions, references, call graphs). Prefer it for code questions; use Grep/Glob for non-code content.

## Tracked agent/docs paths

`.scratch/`, `docs/`, `AGENTS.md`, `CONTEXT.md`, `INBOX.md`, and `.kimi-code/` are tracked in git (shared across machines). Run data (`v2/baselines/`, `v2/logs/`, `v3/runs/`, `runs_*/`, etc.) stays gitignored. `.kimi-code/mcp.json` holds no secrets — tokens are passed via shell env vars (`GRAFANA_SERVICE_ACCOUNT_TOKEN` for Grafana, `GITHUB_PERSONAL_ACCESS_TOKEN` for the GitHub MCP).

## Save states

Training defaults keep using the four early-game `.state` files at the **repo root** (`init.state`, …) — do not move or delete them; live jobs resolve those paths. The expanded milestone inventory lives in `pyboy_states/` (see that directory's README). Both locations are Frozen and hash-manifested.

## Agent skills

### Issue tracker

Issues and specs live as local markdown files under `.scratch/<feature-slug>/` — not GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles use their default label strings (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`), recorded as `Status:` lines in issue files. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: one `CONTEXT.md` at the repo root plus `docs/adr/`, created lazily by the domain-modeling skill. See `docs/agents/domain.md`.

## Cursor delegation

The `cursor-delegate` MCP exposes exactly three tools: `mcp__cursor-delegate__delegate` (send a task), `mcp__cursor-delegate__cancel` (stop one by sessionId), `mcp__cursor-delegate__doctor` (setup diagnostics).
