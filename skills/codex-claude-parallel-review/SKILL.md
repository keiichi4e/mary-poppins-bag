---
name: codex-claude-parallel-review
description: Run one code review with Codex and Claude Code in parallel over the same local diff, commit range, branch comparison, or GitHub PR, then synthesize one evidence-backed verdict with deduplicated findings and explicit residual risk.
---

# Codex Claude Parallel Review

Use this skill when the user explicitly wants both Codex and Claude Code to review the same change in parallel and receive one merged judgment instead of two disconnected reports.

This skill is for review and synthesis. It doth not apply fixes unless the user later asks for them.

The final output must be priority-ordered. The highest-risk findings come first; trivia may wait its turn like all lesser things.

## When To Use

- The user asks for `codex` and `claude code` to review simultaneously.
- The review target is a local diff, commit range, branch comparison, staged change, or GitHub PR.
- The user wants one final verdict with overlap removed.

## Preconditions

- Delegation is explicitly requested by the user.
- `claude-transport` is available so thou canst reach Claude via tmux.
- A stable review surface can be materialized as files before dispatch.

If thou canst not produce one shared review surface, stop. Two reviewers inspecting different code is theater.

## Review Surface First

Before dispatching either reviewer, materialize the exact change under review and save it to local artifacts.

Supported sources:

- GitHub PR URL
- `git diff --cached`
- `git diff <base>...<head>`
- `git show <commit>`
- path-limited diffs such as `git diff -- path/to/file`

Record, at minimum:

- review target identifier
- compared refs or commit SHA
- changed file list
- full patch artifact

Prefer commands of this shape:

```bash
git diff --stat <base>...<head>
git diff --name-only <base>...<head>
git diff <base>...<head> > /tmp/review.patch
git show --stat --name-only <commit>
git show <commit> > /tmp/review.patch
gh pr view <PR_URL> --json number,title,baseRefName,headRefName,url
gh pr diff <PR_URL> > /tmp/review.patch
```

If the user provides a narrower scope, generate artifacts for that scope and pass the same boundary to both reviewers.

Read the patch thyself before dispatch. A synthesizer who hath not seen the code is but a parrot in robes.

## Dispatch In Parallel

Both reviewers must receive the same:

- review target description
- file list artifact
- patch artifact path
- scope boundary
- review contract
- priority model

### Reviewer A: Codex

Spawn one read-only sub-agent. Prefer `explorer` unless a broader reasoning model is plainly needed.

Prompt skeleton:

```text
Review this change using the provided patch artifact and file list as the only review surface.

Target: <target>
Scope: <scope or entire change>
Patch: <path>
Files: <path>

Return only evidence-backed findings. For each finding include:
- severity: blocking | warning | nit
- priority rank within your own findings, highest first
- file:line when available
- why it matters
- the behavioral or maintenance risk

Also include:
- items considered and rejected
- verdict: approve | merge_with_minor_changes | request_changes | needs_discussion
- explicit "no actionable findings" if none survive
```

### Reviewer B: Claude Code

Use `claude-transport` and a response file. Claude must review the same saved artifacts, not an independently reconstructed diff.

Preferred pattern:

```bash
RESPONSE_FILE="/tmp/claude-review-$(date +%s).md"
~/.codex/skills/claude-transport/scripts/tmux-claude.sh \
  "Review this change using only the supplied artifacts. Target: <target>. Scope: <scope>. Patch: <patch_path>. Files: <files_path>. Write structured findings to: $RESPONSE_FILE"
```

Require the same contract from Claude:

- `blocking`, `warning`, `nit`
- highest-priority findings first
- file:line references when possible
- concise evidence and rationale
- rejected non-issues
- verdict
- explicit no-finding statement when appropriate

After sending the tmux message, immediately post the local digest required by `claude-transport`.

## Priority Model

Use this weighting model during dispatch and synthesis:

- `blocking`: 100
- `warning`: 40
- `nit`: 10

Add synthesis modifiers:

- `+25` if both reviewers independently found the same issue
- `+10` if thy own re-check confirms the finding cleanly
- `-15` if the evidence is real but incomplete or partly inferential
- `-30` if the claim survives only as a discussion point

The precise arithmetic mattereth less than consistency. The goal is stable ordering: correctness and regression risks first, maintainability second, polish last.

## Collection

Do not synthesize early because one reviewer finished first.

Collect:

- Codex review output
- Claude review output
- patch artifact
- file list artifact

If one reviewer fails, say which one failed and continue only if the remaining review is still useful. Mark confidence as reduced.

## Synthesis

Do not concatenate raw findings. Judge them.

### 1. Normalize

Turn each finding into:

- reviewer
- severity
- weight
- claim
- evidence
- file and line
- whether thy own re-check confirmed it

### 2. Deduplicate

Merge findings that describe the same defect, even if one names the cause and the other the symptom.

When merging:

- keep the clearest wording
- preserve reviewer attribution
- increase confidence when both found the same issue

### 3. Resolve Disagreement

When reviewers disagree:

- re-check the diff and surrounding code thyself
- prefer the claim with direct code evidence
- if neither side proves the matter, keep it only as `needs_discussion`
- if one reviewer cited stale context or code outside the review surface, discard that claim

### 4. Re-check

For every surviving finding, inspect the patch and surrounding code thyself.

Drop or downgrade findings that are:

- unsupported by the diff
- outside the agreed scope
- speculative without concrete failure mode
- invalidated by nearby code the reviewer ignored

### 5. Recalibrate Severity

- `blocking`: correctness bug, regression risk, security issue, data loss risk, or missing test for meaningful behavior change
- `warning`: robustness, design, maintainability, or test gap worth fixing before merge
- `nit`: local polish with low risk

### 6. Score And Sort

Assign each surviving finding a final weighted score using the priority model above.

Sort the final finding list by:

1. weighted score, descending
2. severity, in the order `blocking` > `warning` > `nit`
3. reviewer agreement, with multi-reviewer findings first
4. file and line for stable presentation

If two findings are close in score, prefer the one with clearer user impact over the one with mere stylistic concern.

### 7. Final Verdict

Return one of:

- `approve`
- `merge_with_minor_changes`
- `request_changes`
- `needs_discussion`

Guidance:

- any surviving `blocking` finding usually means `request_changes`
- only `nit` findings usually means `merge_with_minor_changes`
- unresolved architectural disagreement means `needs_discussion`

## Output

Present findings first.

```markdown
Verdict: request_changes

Findings
1. [blocking][score: 135] path/to/file.ts:42
   Claim.
   Evidence: what in the change proves it.
   Reviewers: Codex, Claude Code

2. [warning][score: 50] ...

Open Questions
- Include only genuinely unresolved points.

Residual Risk
- Note unreviewed areas, failed reviewer runs, or missing verification.
```

If no actionable findings survive, say so plainly and still mention residual risk.

## Guardrails

- Never claim agreement unless both reviewers truly agreed.
- Never surface a finding without code evidence.
- Never let either reviewer's confidence outrun the proof.
- If thou editest code after review, all prior findings are stale; rerun both reviewers.
- If the change is feature-flagged, require tests for both flag states. Flag OFF must preserve prior behavior.
- Never ask Claude to make code changes; this skill is review-only.

## Invocation Pattern

Prefer prompts of this shape:

```text
Use $codex-claude-parallel-review to review the current branch diff against main.
Have Codex and Claude Code review the same saved artifacts in parallel, rank findings by priority, then merge the results into one final verdict with issues sorted by weighted importance.
```

```text
Use $codex-claude-parallel-review to review https://github.com/<owner>/<repo>/pull/<number>.
Run Codex and Claude Code in parallel on the same patch artifact, request priority-ranked findings, and return one evidence-backed verdict with the final issue list sorted by weighted importance.
```
