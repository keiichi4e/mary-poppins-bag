---
name: linear-team-transfer
description: Move Linear issues or projects from one team to another with a safe, repeatable workflow. Use this skill when the user wants to re-home work between Linear teams, bulk-check the impact first, or execute the move via the Linear GraphQL API instead of clicking through the UI.
---

# Linear Team Transfer

Use this skill when work in Linear must be moved from one team to another and the change should be previewed before execution.

The bundled script prefers determinism over cleverness:

- It reads the live GraphQL schema before mutating anything.
- It supports `--dry-run` for both issue and project moves.
- It prints the before/after team mapping so the caller can sanity-check the change.

## When To Use

- Move one issue from team A to team B.
- Move one project from team A to team B.
- Verify whether a project is multi-team before changing it.
- Avoid losing context by checking Linear's documented move caveats first.

## Preconditions

Set one of these environment variables:

- `LINEAR_API_KEY`
- `LINEAR_AUTH_HEADER`

`LINEAR_API_KEY` is treated as a personal API key unless it already begins with `Bearer `. Per Linear's GraphQL docs, personal API keys are sent as `Authorization: <API_KEY>`, while OAuth tokens use `Authorization: Bearer <ACCESS_TOKEN>`.

## Workflow

1. Confirm the destination team.
   Run `python3 skills/linear-team-transfer/scripts/linear_team_transfer.py list-teams`
2. Preview the move.
   Always run the same command once with `--dry-run`.
3. Execute the move.
   Re-run without `--dry-run` only after the preview matches intent.
4. Summarize side effects.
   For issue moves, remind the user that Linear changes the issue ID and may drop cycle, team-label, or project associations unless the destination team is already on the project.

## Commands

List teams:

```bash
python3 skills/linear-team-transfer/scripts/linear_team_transfer.py list-teams
```

Preview an issue move:

```bash
python3 skills/linear-team-transfer/scripts/linear_team_transfer.py move-issue \
  --issue ENG-123 \
  --target-team "Platform" \
  --dry-run
```

Execute an issue move:

```bash
python3 skills/linear-team-transfer/scripts/linear_team_transfer.py move-issue \
  --issue ENG-123 \
  --target-team "Platform"
```

Preview a project move:

```bash
python3 skills/linear-team-transfer/scripts/linear_team_transfer.py move-project \
  --project 01234567-89ab-cdef-0123-456789abcdef \
  --source-team "Core Product" \
  --target-team "Platform" \
  --dry-run
```

Execute a project move:

```bash
python3 skills/linear-team-transfer/scripts/linear_team_transfer.py move-project \
  --project 01234567-89ab-cdef-0123-456789abcdef \
  --source-team "Core Product" \
  --target-team "Platform"
```

## Notes On Entity IDs

- Issues may be addressed by Linear issue key such as `ENG-123`; Linear's developer docs show `issue(id: "BLA-123")` and `issueUpdate(id: "BLA-123", ...)`.
- Projects should be addressed by UUID. In Linear UI, open the command menu and use `Copy model UUID`.
- Teams may be referenced by UUID, key, or exact name. The script resolves whichever matches uniquely.

## Project Move Semantics

Projects in Linear can belong to one or many teams. This skill treats a "move" as:

- remove the source team from the project's team set, when `--source-team` is provided
- add the target team if absent

If the project is already attached to multiple unrelated teams, the script preserves them unless the user explicitly chooses one as `--source-team`.

## Failure Handling

- If team resolution is ambiguous, stop and ask the user to supply a UUID.
- If GraphQL introspection shows that the workspace schema lacks the expected project mutation fields, stop and report the discovered fields instead of guessing.
- If any mutation runs, do not claim success until the returned entity reflects the new team association.

## Source Notes

- Linear developer docs: the GraphQL endpoint supports introspection, and `issueUpdate` accepts an `id` plus `input` fields.
- Linear user docs: moving an issue to another team changes its issue ID and can remove cycle, team-label, and project associations.
- Linear docs: projects can belong to one or many teams.
