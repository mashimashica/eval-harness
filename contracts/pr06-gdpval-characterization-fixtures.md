<!--
SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# PR06 GDPval baseline characterization and fixture matrix

## Evidence boundary

All observations in this document come from source commit `d5ce0c10162cad788a17cb90f34b8f60574e7f75` (tree `354943ebbb8ea81a30523bfdc12baf26771853b5`). Characterization used deterministic fake clients and temporary files; it made no model or provider calls. The repository was not edited.

The following baseline tests were also run with Python 3.13.14 and passed:

- four focused GDPval app tests: missing rubric, missing reference, isolated reference failure, and all-reference failure;
- all 18 tests in `tests/harness/test_pairwise_evaluator.py`, `tests/harness/test_local_judge_pairwise.py`, and `tests/harness/test_local_judge_runner_control.py`; and
- all four tests in `tests/harness/test_local_judge_isolation.py`.

That is 26 selected baseline tests. The isolation tests used fake CLI processes and temporary paths; they made no subscription or model call.

The tables distinguish two expectations:

- **Mechanical parity** means PR06 must preserve the result for valid inputs while moving it behind verified bundles, an anonymous projection, and the common runner.
- **Revision change** means the current result is unsafe or ambiguous. PR06 must assign a new evaluator/parser revision and produce the explicit fail-closed result shown here. A profile may choose a supported partial-trial policy; its policy and threshold enter the evaluator configuration digest.

## Reviewed bytes

| Path | Git blob | Bytes | SHA-256 |
|---|---|---:|---|
| `resources_servers/gdpval/app.py` | `25edad0f2f11adff3d480f996a645a2161c072b1` | 44,786 | `f4f84f4de434a5f815ca60f23081d2de13ef4b7f13988714cc92ee8f536c9e1b` |
| `resources_servers/gdpval/scoring.py` | `d8646f79482e7775e8f3aba3558479656bf881ba` | 23,089 | `6671b93ac60e19e14de496b019aa3b034091c1a4c30334b81077c7c61e1aa501` |
| `resources_servers/gdpval/comparison.py` | `5bb7dbcce2096bcfb5b8669dc730fac727e558f6` | 26,478 | `62fb5b3abe7ff27d85325b833c4d62cea03c42aff96d44c06e2cf7035e1e6a4b` |
| `resources_servers/gdpval/judge_panel.py` | `b46a7d893a4974c4172bf5d39097938aed0af63f` | 7,258 | `8b5355c3226826c4272b58dda560204bd249c80a56b1985a16f88b43992a076e` |
| `resources_servers/gdpval/preconvert.py` | `6b88b4197164dc76af3b24028a3a864b6c4bd94c` | 8,183 | `9a25d1a735b15037cfc455a425ac4e341923309f67edd842dc5abc70c2a98a49` |
| `resources_servers/gdpval/prompts/judge_prompt.j2` | `0285b21e5fb8f0930037d805715fcb6eedd67cb6` | 1,436 | `f0af9a09cb0e067c53a7e51922064d89092dbc01857268add93e78d519587768` |
| `responses_api_agents/stirrup_agent/file_reader.py` | `892854920e45b8c8bba23a3e6a81745b88384193` | 10,813 | `919f3f39b8f32499185880ff4cb1e392d333c79f7a2d68984542f02f5ac37d97` |
| `eval_harness/local_judge_runner.py` | `db6822eeb81674dd1952cdf4d7bebd172a3944a4` | 23,874 | `5afe58f075ab456056b65da8eb4c97a16ae920f7d025a81f273465f90411b5dd` |
| `eval_harness/evaluators/base.py` | `58b31bff614555143b31278e4ac5a1ffdb7b6602` | 8,197 | `8bc22620130411530975dc3330ebbde11c6df6e77e0695f14152c14be5b76839` |
| `eval_harness/evaluators/gdpval.py` | `4314fc5c9901dc36bce0f045f12a2f9321c790bb` | 14,062 | `2e4ba742a53aa726785b9c1231ca84bf081cdd4ab82ed1bc9a392af7a58c4bd2` |
| `eval_harness/evaluators/pairwise.py` | `fba665b0ae0b394ffc7a815c7bffc772460476e5` | 17,600 | `dc614080d4a5fafb9de0bfd5b6fcee3ea44e7f46faacd82229f8468ee36aa37b` |
| `eval_harness/judges/base.py` | `c8bdd1e790edaef3c0c4f1f028b09333fb5b38cd` | 2,029 | `ba464f203083858bc34afbd46ad11bcb57ebbc5a1fe30b5da6ee8f75b4b90da6` |
| `eval_harness/judges/pairwise.py` | `290fef2944b7d7e3de2671981600d1154c8f83fd` | 10,397 | `cc784d953bd1fc644f846a398e65ebfe22304715fed9d7b920b24c72717b4a11` |
| `eval_harness/judges/codex.py` | `758461713e08614cb2381506fed9470fde072ae6` | 16,587 | `e367f72191e6f59d939a9d5c4adc133b93d3756dee85ac3eb5523ad4d64c11fc` |
| `eval_harness/judges/claude_code.py` | `32dd0de288fd47f12ee30e2e73009040fefc6969` | 10,479 | `0db6e3e193a0d9d4726558bbcd08d572a63d759aaf151581ed490ff73f954cc5` |
| `eval_harness/executors/codex.py` | `3c037656375cedf2d83f3f8604746f34952305b3` | 13,478 | `6e27349ffa2b35029276bf29aae66875c51a4d4188d8ad8621aea521cd2f4642` |
| `eval_harness/executors/claude_code.py` | `e1a6739a61dc11ff5e6f37b60023d3c466a0cfec` | 13,483 | `345434b2c68d3c75a821505809795a3af1e9586b8796b0c5cdda44b8ab9b5f8a` |
| `eval_harness/candidate_bundle.py` | `fdc93ec63392b7cad6a0750d454a54e3d3306d25` | 80,356 | `ffcd8a0a5f918754be3f034a86326b0ff914e6f91bcd2bad4d4c214bee459f61` |
| `eval_harness/benchmarks/snapshot.py` | `cdcceed76b0c2d80b4afaf67295a0def306ce944` | 64,984 | `49613424fcd02faa4508be9fcc88947b6d45a99cfdbb14b24ab79dce8396f379` |
| `tests/harness/test_local_judge_isolation.py` | `064fb6b671d37e0ef498a2da3018f1954e94e80a` | 4,753 | `e25d5b15fbb4386d5058057452880c2ee06dbecace233c828b1e3fcdd8cda0be` |

## Pairwise verdict fixtures

`resources_servers.gdpval.comparison.parse_judgement` uses case-sensitive substring tests in A, B, TIE order. Its exact current outputs are:

| Input | Current output | PR06 revised output |
|---|---|---|
| empty string | `BOXED[TIE]` | status `invalid_response`, verdict `null` |
| `not a verdict` | `BOXED[TIE]` | status `invalid_response`, verdict `null` |
| `boxed[a]` | `BOXED[TIE]` | completed verdict `A` (strict parser is case-insensitive) |
| `BOXED[B]` | `BOXED[B]` | completed verdict `B` |
| `BOXED[A] and BOXED[B]` | `BOXED[A]` | status `invalid_response`, verdict `null` |
| `BOXED[TIE] trailing` | `BOXED[TIE]` | status `invalid_response`, verdict `null` because the standalone verdict must be the final nonempty line |
| reasoning followed by a standalone `BOXED[TIE]` line | `BOXED[TIE]` | completed verdict `TIE` |

The already accepted strict parser in `eval_harness/judges/pairwise.py` produces these exact `ValueError` messages:

```json
{
  "": "judge output is empty",
  "not a verdict": "judge output must end with exactly one standalone BOXED[A], BOXED[B], or BOXED[TIE] verdict",
  "BOXED[A] and BOXED[B]": "judge output must end with exactly one standalone BOXED[A], BOXED[B], or BOXED[TIE] verdict",
  "BOXED[TIE]\ntrailing": "judge output must end with exactly one standalone BOXED[A], BOXED[B], or BOXED[TIE] verdict"
}
```

PR06 mechanically reuses that strict protocol. Changing malformed output from tie to invalid is the `gdpval.pairwise@2` revision change.

### Reversal, tally, and trial count

For legacy responses `[A, A, invalid, B]` over four trials, even indices are unswapped and odd indices are swapped. The exact current result is:

```json
{
  "winner": "BOXED[A]",
  "win_count_a": 2,
  "win_count_b": 1,
  "tie_count": 1,
  "task_count": 4,
  "per_judge": {
    "only": {
      "win_count_a": 2,
      "win_count_b": 1,
      "tie_count": 1,
      "trials": 4
    }
  },
  "trial_judges": ["only", "only", "only", "only"],
  "raw_responses": [
    "reason\nBOXED[A]",
    "reason\nBOXED[A]",
    "not a verdict",
    "reason\nBOXED[B]"
  ]
}
```

Under PR06 the same valid A/A/B verdicts normalize to logical A wins `2`, logical B wins `1`, while the malformed trial becomes an `invalid_response` attempt record and contributes no tie. With `completion_policy=require_complete`, the evaluation has status `failed` and no official winner/score. With a profile-selected `valid_only` policy whose threshold is met, the outcome may be A with explicit `valid_trials=3`, `requested_trials=4`, `coverage=0.75`, `invalid_trials=1`, and evaluation status `partial`. The policy/threshold are included in the configuration hash.

Calling legacy `run_trials(..., num_trials=0)` yields:

```json
{
  "winner": "BOXED[TIE]",
  "win_count_a": 0,
  "win_count_b": 0,
  "tie_count": 0,
  "task_count": 0,
  "per_judge": {},
  "trial_judges": []
}
```

PR06 rejects a non-positive trial count in preflight. This is part of `gdpval.pairwise@2`.

The pure accepted normalizer remains mechanical parity:

```json
{
  "unswapped": {"A": "A", "B": "B", "TIE": "TIE"},
  "swapped": {"A": "B", "B": "A", "TIE": "TIE"}
}
```

The pure accepted aggregate for `[A, B, TIE, A]` is `{"wins_a":2,"wins_b":1,"ties":1,"trials":4,"score_a":0.625}`. Its empty aggregate is `{"wins_a":0,"wins_b":0,"ties":0,"trials":0,"score_a":0.0}`; PR06 must never publish that empty numeric result as a completed evaluation.

### Position-policy fixtures

Legacy GDPval always uses `[false, true, false, true]` for four trials, where `true` means the logical candidates are swapped in the presented A/B slots. The existing generic pairwise helper instead seeds its first position. For seed 42 it produces:

```json
{
  "task-001": {"initial_swap": false, "trials": [false, true, false, true]},
  "task-alpha": {"initial_swap": true, "trials": [true, false, true, false]},
  "task-beta": {"initial_swap": true, "trials": [true, false, true, false]}
}
```

PR06 exposes named policies rather than hiding either rule: `alternating-a-first-v1`, `alternating-seeded-v1`, and `explicit-slots-v1`. The fully resolved per-trial slot plan is persisted before the first judge call. AA-v2 selects explicit legacy slots in PR08 without reimplementing reversal.

### Reward conversion

Current `compute_comparison_reward` returns:

```json
{"BOXED[A]": 0.0, "BOXED[B]": 1.0, "BOXED[TIE]": 0.5, "garbage": 0.5}
```

The first three mappings are mechanical parity when A is the reference and B is the evaluated candidate. The fourth is removed by `gdpval.pairwise@2`: an unrecognized value cannot reach reward conversion.

## Rubric fixtures

### Binary/visual JSON scoring

With one fake judge named `only`, the exact current outputs are:

| Response text | Current `(score, metadata)` | PR06 `gdpval.rubric.binary@2` |
|---|---|---|
| `{"criteria_scores":[{"score":1},{"score":0.5}` | `(0.75, null)` | `invalid_response`, score `null`; recovered values may be diagnostic only |
| `{"foo":"bar"}` | `(0.0, {"foo":"bar","judge_name":"only"})` | `invalid_response`, score `null` |
| `{"criteria_scores":[{"score":1},{"score":0.4},"ignored"]}` | `(0.7, metadata-with-the-same-criteria-and-judge)` | completed score `0.7` (mechanical valid-score parity) |
| `{"overall_score":1.25}` | `(1.0, {"overall_score":1.25,"judge_name":"only"})` | completed score `1.0` if finite numeric clamping is retained by configuration |
| `{"overall_score":-2}` | `(0.0, {"overall_score":-2,"judge_name":"only"})` | completed score `0.0` if finite numeric clamping is retained by configuration |
| `{"overall_score":true}` | `(1.0, {"overall_score":true,"judge_name":"only"})` because `float(True) == 1.0` | `invalid_response`, score `null`; booleans are not numeric scores |
| `{"overall_score":0.1,"overall_score":0.9}` | `(0.9, {"overall_score":0.9,"judge_name":"only"})` because `json.loads` keeps the last duplicate key | `invalid_response`, score `null`; duplicate keys are ambiguous |
| `{"overall_score":"nan"}` | `(1.0, {"overall_score":"nan","judge_name":"only"})` | `invalid_response`, score `null` because non-finite values are forbidden |

When raw response retention is enabled, a successful metadata object also gets `"raw_responses":[<exact response text>]`; the truncated case still returns null metadata. PR06 stores every attempt's raw-response digest and configured evidence reference, including invalid attempts.

The current precedence for a valid overall score is `overall_score`, `total_score`, `score`, `average_score`, then `final_score`. If none exists, current code averages `criteria_scores[*].score` for dictionary entries, using zero when an entry lacks `score`. PR06 preserves this precedence and finite numeric clamping as pure scoring policy. JSON parse failure, absence of every score source, boolean/float conversion ambiguity, duplicate keys, and non-finite values become typed invalid responses under revision 2.

The binary template is 1,436 UTF-8 bytes with SHA-256 `f0af9a09cb0e067c53a7e51922064d89092dbc01857268add93e78d519587768`. Rendering the fixture values `Canonical task`, `Pretty rubric`, and `Deliverable` produces 1,399 characters with SHA-256 `eb2cdadcab2f620f7fae53d3ec46816bb79b1b07fe6c403e9e940caa88b15737`.

### Structured tagged scoring

For rubric `[{'score': 2}, {'weight': 3}]`, two trials, and two formatting attempts per trial, responses `[bad, 4/5, 2/99, 2/5]` produce exactly:

```json
{
  "score": 0.6,
  "metadata": {
    "scoring_method": "structured_rubric",
    "scores": [4.0, 2.0],
    "max_possible_scores": [5.0, 5.0],
    "score_percentages": [80.0, 40.0],
    "average_score": 3.0,
    "overall_score_percentage": 60.0,
    "max_possible_score": 5.0,
    "num_trials_completed": 2,
    "num_trials_requested": 2,
    "trial_judges": ["only", "only"],
    "raw_responses": [
      "FINAL_SCORE[4] out of MAX_POSSIBLE_SCORE[5]",
      "FINAL_SCORE[2] out of MAX_POSSIBLE_SCORE[5]"
    ]
  }
}
```

That valid score math is mechanical parity. The failed and max-mismatched formatting attempts are currently absent from metadata; PR06 preserves them as attempt evidence.

For responses `[4/5, bad, still bad]`, one of two requested trials completes. Current output is score `0.8`, `num_trials_completed=1`, `num_trials_requested=2`, `scores=[4.0]`, `score_percentages=[80.0]`, and raw responses containing only the successful `4/5` response. PR06 produces the same numeric score only under an explicit `valid_only` policy with minimum one, and reports `status=partial`, `coverage=0.5`, plus both failed attempt records. `require_complete` produces status `failed` and no official score.

When all four formatting attempts are malformed, current output is:

```json
{
  "score": 0.0,
  "metadata": {
    "error": "no_valid_scores",
    "num_trials": 2,
    "raw_responses": []
  }
}
```

`app.py` marks that response as valid because the metadata dictionary is non-null. PR06 revision 2 returns a failed evaluation with score `null`, two invalid trial records, four attempt records, `valid_trials=0`, and `coverage=0.0`.

The current point maximum is the sum of numeric `score`, else numeric `weight`, for each list item or each item under a dictionary's `criteria`. Missing values contribute zero. With `[{'criterion':'x'}]` and `FINAL_SCORE[999] out of MAX_POSSIBLE_SCORE[-2]`, current output is normalized score `0.0` while metadata says average `999.0`, maximum `-2.0`, and one completed trial. Revision 2 requires a finite positive configured/computed maximum and `0 <= awarded <= maximum`; this fixture fails preflight or parsing and has no score.

The current maximum check uses the inclusive effective condition `abs(parsed_max - computed_max) <= 0.01`. For computed maximum `5`, one trial `FINAL_SCORE[4] out of MAX_POSSIBLE_SCORE[5.009]` is accepted and returns normalized score `0.798562587342783`, while `MAX_POSSIBLE_SCORE[5.011]` is retried/rejected. With multiple valid trials, the current final denominator is the first valid trial's parsed maximum. PR06 preserves this tolerance and first-valid-denominator rule as mechanical rubric-score parity; the planned trial order makes it deterministic, and the accepted parsed maximum is stored in every semantic trial result.

Current `parse_structured_score("FINAL_SCORE[4] FINAL_SCORE[1] MAX_POSSIBLE_SCORE[5] MAX_POSSIBLE_SCORE[9]")` returns `(4.0, 5.0)` by taking the first match of each tag. Revision 2 rejects duplicate/conflicting top-level tags as an invalid response.

The structured prompt constant is 866 characters with SHA-256 `f993ab2daf3a5f7f47cbbac22fe6076f8923d8ce7bbb6b68d7526cf1eee49c72`.

## Resource-server outcome fixtures

These current app outputs define failure-history evidence. They are not response schemas to carry into the new common runner.

| Case | Current selected fields/result | PR06 result |
|---|---|---|
| Missing both rubric forms | `reward=0.0`, `verify_mode="rubric"`, `invalid_judge_response=true`, no judge call | preflight/config failure; no score and no call |
| No attempted reference deliverable | `reward=0.0`, `verify_mode="comparison"`, `judge_response={"error":"reference_missing"}`; no loss flag | verified-plan failure before judging; no score/reward |
| Eval deliverable missing after references exist | `reward=0.0`, `judge_response={"error":"eval_missing"}`, `loss=true` | invalid/missing candidate bundle; no judge call; profile decides denominator outside evaluator |
| One of two reference matchups throws and the survivor has eval wins/losses `3/1` | only survivor appears in `per_reference`; totals wins `3`, losses `1`; reward `1.0`; failed reference appears in `ref_errors`; `reference_count=1` | complete BattleRecords aggregate; missing matchup is explicit coverage loss; supported partial policy decides whether an outcome is publishable |
| Both reference matchups throw `RuntimeError('500 Internal Server Error')` | raises `RuntimeError("all 2 judge matchup(s) failed for task task-1; last error: RuntimeError('500 Internal Server Error')")` | failed evaluation, no score/winner/tie; typed judge failure records retained |

The current app catches at the reference-repeat boundary, so one failing trial causes that whole in-memory matchup result to be discarded. PR06 persists each trial immediately, but `require_complete` preserves the current all-or-nothing matchup eligibility. `valid_only` is reusable generic policy with explicit coverage, never an AA-specific duplicate.

## Judge-panel fixtures

For ordered members `zero(weight=0, AV=false)`, `two(weight=2, AV=false)`, and `av(weight=1, AV=true)`, using `make_rng(42, 'task-001', 'anchor-7', 'repeat_1')`, the first eight current draws are:

```json
["two", "two", "av", "two", "two", "av", "av", "av"]
```

Current panel summary is:

```json
[
  {"name": "zero", "weight": 0.0},
  {"name": "two", "weight": 2.0},
  {"name": "av", "weight": 1.0}
]
```

Non-positive weights are treated as zero; when the total positive weight is zero, current code samples uniformly. A one-member panel bypasses weight handling entirely, so even a non-finite weight selects that member; in a multi-member panel NaN is effectively zero while infinity can make `random.choices` raise. PR06 pins the finite-weight behavior as a named selector revision, rejects every non-finite configured weight, and pre-resolves member IDs for every trial. Member IDs are unique, the ordered member/spec/capability/weight set has a panel digest, and credentials never enter the spec or digest.

Current AV filtering returns `["av"]` for the full panel. For `["zero","two"]` it returns the same incapable full panel. Direct `direct.mp4` and a zip containing `nested/audio.wav` both make `dir_contains_audio_video` return `true`. PR06 changes the incapable fallback under the panel/evaluator revision: capability insufficiency fails preflight before the first call and creates no successful trial records.

PR08 may reproduce its legacy member stream by persisting an explicit draw plan whose input is seed 42 plus task ID, anchor ID, and anchor-repeat directory name. Eval repeat is intentionally absent in that profile rule. PR06 only executes and records the preselected members; it owns no stage, anchor, or Elo meaning. PR08 supplies a stable opaque match-occurrence ID for each resolved stage/task/eval-repeat/anchor-repeat occurrence. Repeated occurrences may share CandidateBundles and `evaluation_input_sha256`, but each gets a distinct `evaluation_job_id` and four fresh legacy judge trials.

## Anonymous projection fixtures

The current strict stager was exercised with task key `task-001`, seed 42, trial 0, identical `reference_files/source.txt`, candidate `answer.txt` values `A` and `B`, and candidate `metadata.json` files. Exact observations:

```json
{
  "swapped": false,
  "reference_tree_hash": "a1057faf6a74066fc5228eaf8cae1c08696f8ed14f427740dd68bf32b3a4543f",
  "submission_a_tree_hash": "42213557f3dd54587b3157fc65a4004931b040bb3d73e8cad2a963641f4dbb2d",
  "submission_b_tree_hash": "fdee33d01762a0298b7d48cefbcb881c58c5b982e868bb9e72f7ffae9ed2b6e1",
  "staged_file_mode": "0444",
  "staged_file_mtime_ns": 946684800000000000,
  "submission_files": ["answer.txt"],
  "metadata_staged": false
}
```

PR06 reuses the byte copy, symlink rejection, normalized modes/times, strict verdict protocol, and logical verdict normalization. It replaces duplicate reference discovery inside candidate directories. One `BoundEvaluationView.allowed_task_inputs` is materialized into anonymous `reference_files`; each verified `CandidateBundle` supplies only its outcome artifacts. The canonical judge task text is `BoundEvaluationView.canonical_task_prompt`, never `effective_executor_prompt`.

The existing generic prompt rendered with `Canonical task` is 676 characters with SHA-256 `be0f88fbcfd48f0d76243d0d349d26586b346510dd68e40dc7e263116bd560ce`. The legacy resource pairwise prefix is 182 characters with SHA-256 `5ff8d28e06b970d1c499f49d1f824e8e75a8e5b5b4a7aaf597c86337c17b8e20`. PR06 must bind the selected prompt asset/revision into its judge-input and evaluator configuration hashes rather than switch prompts implicitly.

## Judge-runtime isolation fixtures

Sanitizing the staged files does not itself blind a local agent, because the agent may try to read other host paths. The baseline has a stricter judge-specific Codex profile than the ordinary application Executor:

| Surface | Ordinary Executor at baseline | Blind-judge adapter at baseline | PR06/PR05 fixture requirement |
|---|---|---|---|
| Codex filesystem | `--sandbox workspace-write`; no root-deny read probe | named profile `gdpval-harness-blind-judge`: `:root=deny`, `:minimal=read`, anonymous workspace and selected command/runtime paths `=read` | An ordinary Executor request without an explicit accepted blind role fails preflight. The neutral role preserves root deny and never allows a runtime path overlapping protected roots. |
| Codex network/config | workspace-write network flag; user config ignored | network disabled, web search disabled, approvals never, ephemeral, user config ignored, no login shell | Fake argv test pins all guards; omitted or overridden guard fails before a model call. |
| Model shell environment | normal executor environment policy | `inherit="none"`; synthetic workspace `HOME`, `PATH=os.defpath`, isolated `TMPDIR`/`TMP`/`TEMP` | Fake runtime observes only the explicit shell values and no candidate/provenance/parent-secret values. |
| Host launcher environment | subscription helper inputs | reviewed runtime/auth-store allowlist | Environment spy proves candidate IDs, labels, bundle/run paths, and unrelated secrets are absent. Auth material is never copied into the anonymous workspace or evidence. |
| Codex auth | accepts positively identified ChatGPT subscription; rejects API/access-token or unknown mode | same, before confinement probe | Exact accepted/rejected auth classifications and zero-call failures are pinned. |
| Codex confinement | none in normal Executor preflight | no-model `codex sandbox` probe reads `workspace/allowed.txt` and must fail to read sibling `outside-secret.txt`; native Windows fails closed | Probe argv and both read outcomes are asserted. A fake sandbox that can read the outside file produces `ok=false` and no judge invocation. |
| Claude filesystem/tools | fail-closed sandbox but no root read deny; Bash/Read/Edit/Write application tools | intended root read/write deny, workspace read allow, empty strict network allowlist, Bash only, Read/Edit/Write/WebFetch/WebSearch/MCP disabled | The judge role must retain these restrictions if a proven adapter becomes available; the ordinary application profile is insufficient. |
| Claude auth/confinement | accepts first-party supported subscription for application execution | recognizes `claude.ai` + `firstParty` + Pro/Max/Team/Enterprise, but still returns `ok=false` because no documented non-model read-confinement probe exists | Preserve the fail-closed result. Settings text alone cannot mark the member available. Console/API, OAuth-token, gateway, Bedrock, Vertex, and Foundry modes remain rejected. |
| Temp/evidence roots | runner-selected | `_safe_temp_parent` searches system temp roots disjoint from candidate A, candidate B, and output; per-run temp vars override caller values | Select a fresh root disjoint from every bundle, snapshot, result, and anonymous workspace; prove the model cannot read the evidence root. |

The four current isolation tests have these concrete observations:

| Baseline test | Fake inputs | Exact observed result | Required migrated assertion |
|---|---|---|---|
| `test_codex_preflight_uses_provenance_free_environment` | fake CLI reports `fake-version`, `Logged in using ChatGPT`, and successful `sandbox`; parent has `GDPVAL_RUN_A=/secret/a`, `GDPVAL_RUN_B=/secret/b`, labels, and `FORBIDDEN_PARENT_SECRET=secret` | `ok=true`, `auth_mode="chatgpt-subscription"`; fake CLI exits successfully only because none of those five variables is present | Port unchanged in meaning; additionally inspect the root-deny probe arguments and verify outside-file denial rather than trusting a constant success exit. |
| `test_claude_preflight_fails_closed_without_non_model_read_probe` | fake auth JSON `{"loggedIn":true,"authMethod":"claude.ai","apiProvider":"firstParty","subscriptionType":"max"}` | `ok=false`, auth mode starts `claude-subscription:`, at least one detail contains `read confinement` | Port unchanged; invocation count stays zero until a documented probe is implemented and tested. |
| `test_safe_temp_parent_rejects_caller_temp_inside_candidate_tree` | caller sets all three temp variables to candidate A | returned parent overlaps neither candidate nor output and is not candidate A | Generalize inputs to both bundles, snapshot/presentation root, result/evidence root, and controller runtime root. |
| `test_runtime_temp_overrides_do_not_copy_parent_temp_paths` | parent temp variables all equal `/candidate/tmp`; explicit fresh runtime path supplied | returned environment sets all three temp variables exactly to the supplied fresh path | Port unchanged in meaning and assert `/candidate/tmp` is absent from all runtime argv, environment values, prompt, and evidence metadata. |

The baseline Codex profile also protects paths derived from `HOME`, `USERPROFILE`, `CODEX_HOME`, `XDG_CONFIG_HOME`, `APPDATA`, `LOCALAPPDATA`, both fixed candidate roots, and the output root; a resolved non-system CLI runtime root is allowed only when it does not overlap any protected path. PR06 replaces the fixed GDPval inputs with the generic plan's complete protected-root set. Preflight evidence binds the role-policy revision/digest and probe result to the attempt record without recording credentials or absolute paths in semantic digests.

For an HTTP or structured multimodal judge, fixtures inspect the full request and prove it contains only the hash-bound anonymous payload. Its explicit endpoint/network/auth policy is recorded without credential values. It is a distinct configured member and never substitutes for a failed local member.

## Presentation fixtures

For top-level files `a.txt = " aye "`, `b.txt = "bee\n"`, `blob.bin = 00 01`, `finish_params.json = {}`, plus nested `nested/ignored.txt`, Stirrup text extraction currently returns exactly:

```text
=== a.txt ===
aye

=== b.txt ===
bee

=== blob.bin ===
[Binary file: blob.bin, 2 bytes]

=== finish_params.json ===
{}
```

Its multimodal block builder returns text blocks for trimmed `a.txt`, trimmed `b.txt`, and `finish_params.json`; it ignores both the binary and nested file. The comparison block builder ignores `finish_params.json` and the nested directory, preserves spaces/newline in text file contents, and emits an orphan filename header for unsupported `blob.bin`:

```json
[
  {"type":"text","text":"\na.txt:\n"},
  {"type":"text","text":" aye "},
  {"type":"text","text":"\nb.txt:\n"},
  {"type":"text","text":"bee\n"},
  {"type":"text","text":"\nblob.bin:\n"}
]
```

A zip with `one/report.txt = one` and `two/report.txt = two` currently flattens both labels to `report.txt`:

```json
[
  {"type":"text","text":"\nreport.txt:\n"},
  {"type":"text","text":"one"},
  {"type":"text","text":"\nreport.txt:\n"},
  {"type":"text","text":"two"}
]
```

PR06's presenter traverses verified artifact/input manifests recursively, retains logical relative paths, performs traversal-safe archive handling when archives are a supported presentation type, and rejects collisions. It never includes bookkeeping, bundle manifests, executor evidence, or condition labels.

The comparison size cap replaces a `250 MiB + 1 byte` `huge.mp4` with `{"type":"text","text":"[oversize: huge.mp4 250.0MB — not included]"}`. PR06 records any permitted omission as presentation status and includes it in the config/input digest; required unsupported or oversized material fails presentation rather than silently reaching a filename-only judgment.

Stirrup Office conversion currently records every returned same-stem PDF as generated and unlinks it after building blocks. With `report.docx` bytes `original-docx`, a pre-existing `report.pdf` containing `preexisting-pdf`, and a fake converter returning that PDF, exact observations are:

```json
{
  "docx_sha256_before_and_after": "a5cc25ff3b85081aa6b469605a2197e3ffd3dba85b6f80423a09f73498481859",
  "pdf_sha256_before": "6a37e385b8379aa9a04b99ab2e757c7bfa9d834ddc182f7e6a527ee41908ed8b",
  "pdf_exists_after": false,
  "pdf_data_url": "data:application/pdf;base64,cHJlZXhpc3RpbmctcGRm"
}
```

`preconvert.py` also writes PDFs beside its input path. PR06 materializes verified bytes to a fresh presentation root and writes every derived file to a distinct derived subtree. A fixture hashes the full source snapshot and both CandidateBundles before and after text, Office, media, and archive presentation; all hashes and bytes must remain identical. Presentation records bind each source logical path/hash to its derived logical path/hash and converter ID/version. Runtime absolute paths and timestamps stay outside semantic digests.

## Failure/status fixture matrix for PR06

| Fixture | Planned calls | Trial records | Evaluation outcome |
|---|---:|---|---|
| Valid binary rubric | 1 | one completed rubric record with finite score | `completed`, one GDPval rubric metric |
| Truncated binary JSON with recoverable numbers | 1 | one `invalid_response`, score null, raw digest retained | `failed`, no metric |
| Structured 2/2 valid | 2 plus formatting attempts | two completed records | `completed`, mean/max normalization matches legacy |
| Structured 1/2 valid, `valid_only(min=1)` | 2 | one completed, one invalid; every attempt retained | `partial`, metric plus coverage `0.5` |
| Structured 1/2 valid, `require_complete` | 2 | same immutable trial evidence | `failed`, no metric |
| Pairwise explicit tie | configured count | exact completed set, at least one explicit TIE | tie votes count as 0.5 only where the protocol aggregate defines it |
| Pairwise malformed output | configured count | malformed attempts are `invalid_response`; no tie vote | partial/failed per hash-bound completion policy |
| Zero pairwise trials | 0 | none | preflight failure, no metric/winner |
| One runtime failure | stops or continues according to typed failure impact | failed record retained; no vote | run-impact systemic failure stops remaining calls; job-impact policy remains explicit |
| Every judge call fails | configured attempts | failed records only | `failed`, no metric/winner/tie |
| AV content, zero capable members | 0 | none | preflight failure `judge_capability_insufficient` |
| Interrupt during call | attempted prefix only | started intent plus interrupted terminal event | `interrupted`, no unresolved work counted; new attempt may resume |
| Resume same completed occurrence | 0 new calls | existing completed semantic record plus intact evidence | reusable only for the same match-occurrence ID after every bound hash is revalidated |
| Identical content in a different planned occurrence | configured new calls | same `evaluation_input_sha256`, distinct job/trial IDs and records | no battle-result deduplication across occurrences |
| Same result after interrupted retry | retry calls only | history/evidence digests differ; completed semantic record digest matches uninterrupted run | identical semantic aggregate, full attempt history retained |

Only an exact valid `BOXED[TIE]` creates a tie. No parser, runtime, presentation, capability, missing-input, zero-trial, or all-judge failure path can synthesize a tie, zero score, half reward, or successful completion.
