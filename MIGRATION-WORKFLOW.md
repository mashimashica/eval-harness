<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Migration checkpoint workflow

This is the operating procedure for the benchmark-neutrality migration.
The canonical control branch is `checkpoint/migration-control`.
Read this file and [the current state](MIGRATION-STATE.md) before starting or resuming work.
The user's migration plan remains the authority for scope, role allocation, and acceptance criteria.

## Save work before validating it

A checkpoint is a durable copy of work in progress. It is not evidence that the code is correct.
Do not wait for a green test suite, completion of a PR, or a reviewer handoff to save work.

Use three separate facts in every report:

| Fact | Required evidence |
| --- | --- |
| Saved | Reachable GitHub commit; branch SHA and changed file bytes read back successfully |
| Validated | Test commands, results, and logs tied to the exact tested commit |
| Accepted | Review decision and all required gates for that migration slice |

A file that exists only in scratch, a tool result, a conversation, or an agent's memory is not a checkpoint.
A source hash without the source bytes is not a recoverable implementation.

## Start each slice with a durable record

1. Read the control branch and verify the current implementation PR heads.
2. Recover and save the exact original plan and the slice's interface contract before implementation.
   Record provenance and file hashes. Do not reconstruct an authoritative contract from a compressed summary.
3. Create `checkpoint/pr-<slice>` from the selected immutable implementation base.
   Record the full base commit, dependency commits, assigned owner, path scope, and the next concrete action.
4. Save that record before editing code. Give collaborators the branch and commit, not a scratch path.

Keep one implementation slice active until its acceptance gates close.
Design and independent review may run in parallel against saved commits.
Preserve the original Astra/Sol/Luna responsibilities; this rule limits unfinished implementation, not review.
Use separate work directories and one writer per branch. Do not share a mutable checkout between owners.

## Checkpoint after every small editing batch

Save changed code, tests, necessary design decisions, and the work record together:

- After a coherent function or file edit, before starting the next independent edit.
- Before a long test, dependency build, review, handoff, pause, or response ending the turn.
- At the next tool boundary after 15 minutes if an editing batch has not finished.

A batch must stay small enough to save at its next boundary.
Keep the uncheckpointed window within one batch; do not accumulate multiple PRs of unsaved code.
If saving fails, stop expanding the unsaved change set and restore persistence first.

Checkpoint steps:

1. Check the exact changed-path allowlist and inspect the diff for accidental files and secrets.
   Exclude credentials, auth stores, unrelated workspace data, and raw private logs.
2. Persist UTF-8 source through GitHub blob, tree, and commit APIs with DCO sign-off.
   Recheck the current branch head and update it without force. Preserve conflicting changes.
3. Read the new ref and changed files back. Verify the returned commit and Git blob hashes.
4. Only then record or report the batch as saved. Record test status separately, including failures and not-run checks.

Do not rely on an unreferenced Git blob or a successful upload response alone.
Keep checkpoint history reachable. Do not delete or rewrite it until all needed changes and records have been
promoted to the implementation stack and read back successfully.

## Preserve a small work record with each code checkpoint

The record belongs in the same commit as the changed source. It contains:

- Slice, owner, base commit, dependency commits, path scope, and contract file paths/hashes.
- What changed and which invariants need checking.
- Validation already run: exact tested commit, command, result, and durable log or decisive summary.
- Validation not run, known failures, blockers, and the next concrete command or edit.
- Promotion status and the formal PR/head, if one exists.

The record need not contain its own commit SHA; the enclosing Git commit identifies it.
After publishing the code checkpoint, update the control state with its reachable branch and commit.
A lag in the central index must not make the code branch unrecoverable: enumerate `checkpoint/*` on recovery.

Preserve source and lock files needed to reproduce builds.
Keep decisive validation summaries in Git; CI artifact URLs alone may expire.
Do not store credentials or model prompts containing private data just to make a checkpoint comprehensive.

## Promote deliberately and keep full quality gates

Checkpoint branches have no formal PR. A failed or untested checkpoint is still worth saving.

After the scoped local checks and source review, transfer the reviewed code delta to the next migration PR branch.
Open or update a Draft PR for full CI. Keep saving continuing work on its checkpoint branch, then promote reviewed
batches to the formal PR; do not run the entire CI suite for every intermediate save.
The formal PR base, parent commits, and changed-path scope must remain explicit.

After promotion, verify the resulting source bytes and run the required gates on the resulting head.
Any changed head invalidates the previous head's validation claim.
Intermediate synthetic merge checks must record their actual commit/tree relationship.
The migration's final acceptance still requires the exact final head, deterministic tests, Ruff, strict typing,
coverage of at least 96% using the integer threshold, vulnerability checks, removal of old routes, and the fourth
benchmark extension test. A checkpoint or focused test percentage cannot replace these requirements.

Keep PRs Draft and do not merge, release, publish, or run real-model experiments in this phase.

## CI behavior of checkpoint branches

The workflows were inspected at `d5ce0c10162cad788a17cb90f34b8f60574e7f75`.

- Eval Harness CI runs for pull requests and pushes to `main`.
- Lint, copyright, and secret PR checks do not run for a normal push to a checkpoint branch without a PR.
- Release and mirrored-PR push patterns do not match `checkpoint/*`.
- The NVSkills push listener has a signature-actor/message condition; it is not a normal full-test checkpoint gate.

No workflow, required check, or acceptance threshold is changed by this procedure.
Recheck triggers if the implementation base changes its workflows.
Do not create a PR, invoke a bot comment, or dispatch a workflow merely to save an intermediate checkpoint.

## Recover after an interruption

1. Read this control branch from GitHub. Verify the recorded PR heads and enumerate `checkpoint/*`.
2. Fetch the selected immutable commit into a fresh directory and verify its tree and file hashes.
   Recover the work record and exact contract with the source.
3. Recreate dependencies from recorded versions and lock files.
4. Treat interrupted validation as not completed. Re-run the affected checks on the restored head.
5. Continue from the recorded next action. Do not silently rebuild already validated slices or infer that missing
   unpublished source exists because a previous conversation reported passing tests.

A crash can still interrupt the current small editing batch.
This procedure protects completed checkpoints and limits reconstruction to the in-flight batch.
