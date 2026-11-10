# Mary Poppins Bag

This repository currently contains a Codex skill for moving Linear issues and projects between teams.

## Linear MCP Setup

The skill is easiest to use once Codex can talk to Linear through MCP.

### 1. Add the Linear MCP server

Run:

```bash
codex mcp add linear --url https://mcp.linear.app/mcp
```

This writes the following stanza to your Codex config:

```toml
[mcp_servers.linear]
url = "https://mcp.linear.app/mcp"
```

On this machine, the config file lives at:

- `~/.codex/config.toml`

In this setup, `~/.codex` is symlinked to:

- `/Users/keiichi.inoue/src/ai-config/codex`

### 2. Complete OAuth login

If Codex detects OAuth support, it prints an authorization URL. Open it in the browser and finish the Linear approval flow.

If needed, you can retry login directly:

```bash
codex mcp login linear
```

### 3. Verify the MCP entry

Check the configured server:

```bash
codex mcp get linear
```

List all configured MCP servers:

```bash
codex mcp list
```

Expected details include:

- `transport: streamable_http`
- `url: https://mcp.linear.app/mcp`

If the current Codex session still does not expose Linear tools after setup, start a new session or restart the app so it reloads MCP servers.

## Linear Team Transfer Skill

The skill lives here:

- `skills/linear-team-transfer`

Main files:

- `skills/linear-team-transfer/SKILL.md`
- `skills/linear-team-transfer/scripts/linear_team_transfer.py`

### List teams

```bash
python3 skills/linear-team-transfer/scripts/linear_team_transfer.py list-teams
```

### Preview an issue move

```bash
python3 skills/linear-team-transfer/scripts/linear_team_transfer.py move-issue \
  --issue ENG-123 \
  --target-team Platform \
  --dry-run
```

### Preview a project move

```bash
python3 skills/linear-team-transfer/scripts/linear_team_transfer.py move-project \
  --project 01234567-89ab-cdef-0123-456789abcdef \
  --source-team "Core Product" \
  --target-team Platform \
  --dry-run
```

## Notes

- The script reads the live Linear GraphQL schema before mutating anything.
- Issue moves can change the issue identifier and may drop cycle, team-label, or project associations.
- Run every move once with `--dry-run` before executing it for real.

## Readable Docs Skill

Style and layout rules for documents other people will read (reports, test plans, Google Docs, Linear docs, email bodies): polite Japanese (desu/masu), headings capped at h2, prose for explanations, tables for comparisons, minimal bullets, emoji status markers, and fact-only reporting.

- `skills/readable-docs/SKILL.md`

### Use it locally

Symlink the skill into the agent's skill directory:

```bash
mkdir -p ~/.claude/skills && ln -sfn "$PWD/skills/readable-docs" ~/.claude/skills/readable-docs
ln -sfn "$PWD/skills/readable-docs" ~/.codex/skills/readable-docs
```

Start a new Claude Code or Codex session afterwards so the skill is picked up.
